#!/usr/bin/python2.5
#
# Copyright 2012 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

"""Handle the weekly snippet digest emails."""

__author__ = 'erichiggins@gmail.com (Eric Higgins)'

import datetime
import logging
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'appengine_config'
from google.appengine import dist  # pylint: disable-msg=C6204
dist.use_library('django', '1.1')
from google.appengine.api import mail  # pylint: disable-msg=C6204
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.api.labs import taskqueue
from google.appengine.ext import deferred
from google.appengine.ext import ereporter
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util as webapputil
from google.appengine.runtime import DeadlineExceededError
import models
import pytz
import util


ereporter.register_logger()


class SnippetFetchWorker(webapp.RequestHandler):
  """Worker designed to fetch and mail a user their snippets."""

  def get(self):  # pylint: disable-msg=C6409
    """Handle initial request and spawn a fetch worker."""
    now = datetime.datetime.now(pytz.utc)
    use_force = bool(self.request.get('use_force', False))
    is_cron = self.request.headers.get('X-Appengine-Cron') == 'true'
    logging.info('Headers %s', self.request.headers)
    user = users.get_current_user()
    try:
      offset = int(self.request.get('offset', default_value=0))
    except ValueError:
      offset = 0
    params = {
        'offset': offset,
        'utc_reset_day': now.weekday(),
        'utc_reset_hour': now.hour,
    }
    if use_force:
      params['use_force'] = '1'
    if is_cron:
      params['is_cron'] = '1'
    if user:
      params['email'] = user.email()
    logging.info('Starting fetch chain with params %s', params)
    fetch_task = taskqueue.Task(url='/report/fetch', params=params)
    fetch_task.add(queue_name='snippet-fetch-queue')

    if not is_cron:
      return self.redirect('/?msg=Snippets+sent.')

  def post(self):  # pylint: disable-msg=C6409
    """Fetch the snippets for this user and create a mail-worker if needed."""
    is_cron = bool(self.request.get('is_cron'))
    last_cursor = self.request.get('cursor')
    cursor = None
    utc_reset_day = int(self.request.get('utc_reset_day'))
    utc_reset_hour = int(self.request.get('utc_reset_hour'))
    offset = int(self.request.get('offset', 0))
    user = users.get_current_user()
    email = self.request.get('email')
    if email and not user:
      logging.info(email)
      user = users.User(email)
    use_force = False
    logging.info('fetch worker called. is_cron: %s, user: %s, cursor: %s',
                 is_cron, user, last_cursor)
    if user and users.is_current_user_admin():  # Only admins may use force.
      use_force = bool(self.request.get('use_force'))
      logging.info('admin %s requests use of force %s!', user.email(),
                   use_force)
    if last_cursor:  # If last_cursor exists, it must persist and continue.
      logging.info('last_cursor exists, setting is_cron and use_force to True.')
      is_cron = True
      use_force = True

    if is_cron or use_force:  # Fetch all users.
      logging.info('fetching next user...')
      offset = 1
      user_query = models.SnippetUser.all()
      user_query.filter('mail_snippets =', True)
      user_query.filter('utc_reset_day =', utc_reset_day)
      user_query.filter('utc_reset_hour =', utc_reset_hour)
      if last_cursor:
        user_query.with_cursor(last_cursor)
      snipper_user = user_query.order('User').get()
      if not snipper_user:  # No more users, time to quit.
        logging.info('No more users, delete the cursor and quit.')
        return
      user = snipper_user.User
      cursor = user_query.cursor()
      logging.info('Found user %s and stored cursor %s.', user, cursor)
    else:
      logging.info('fetching single user...')
      offset = int(self.request.get('offset', default_value=0))
      snipper_user = models.GetSnippetUser(user)

    logging.info('User is %s', user)
    if user is None:
      return
    # Get snippets.
    if is_cron or use_force:
      # TODO(erichiggins): Clean this up. Consider verifying the dates from
      # GetLastWeekday and use that to determine the proper offset value.
      # Just get snippets from 7 days ago until now.
      start_date = (datetime.datetime.utcnow().replace(second=0, microsecond=0)
                    - datetime.timedelta(days=7))
      query = models.Snippet.all().filter('User =', user)
      query.filter('DateStamp >=', start_date)
      query.order('DateStamp')
      snippet_results = query.fetch(limit=1000)
    else:
      # Clear out memcache, the reset messes up results.
      memcache.delete_multi(['snippets_%s_%d' % (str(user), x) for x in (0, 1)])
      snippet_results = models.FetchSnippets(user=user, offset=offset)
    logging.debug('%s has %s snippets.', user.nickname(), len(snippet_results))

    if snippet_results:
      user_tz = pytz.timezone(snipper_user.timezone)
      datestamp = util.GetLastWeekDay(utc_reset_day,
                                      offset=offset,
                                      hour=utc_reset_hour,
                                      tz=pytz.utc)
      snippet_format = snipper_user.snippet_format
      date_format = str(snipper_user.date_format)
      datestamp = datestamp.astimezone(user_tz).strftime(date_format),
      # Format each snippet according to the user's preference.
      try:
        snippets = [snippet_format % s.Snippet for s in snippet_results]
      except TypeError:
        logging.debug('%s has an invalid snippet_format: "%s"',
                      user, snippet_format)
        snippets = ['- %s' % s.Snippet for s in snippet_results]
      if snippets:
        # Add a task to the queue to send an email to each snipper user.
        mail_params = {
            'user': user.nickname(),
            'email': user.email(),
            'datestamp': datestamp,
            'snippets': '\n'.join(snippets),
        }
        logging.info('Creating mail task with params: %s', mail_params)
        mail_task = taskqueue.Task(url='/report/mail', params=mail_params)
        mail_task.add(queue_name='snippet-mail-queue')
      else:
        logging.info('No snippets to mail...')
    else:
      logging.info('snippet_results is empty...')

    if is_cron:  # Run the next fetch worker.
      params = {
          'is_cron': is_cron,
          'offset': offset,
          'use_force': int(use_force),
          'utc_reset_day': utc_reset_day,
          'utc_reset_hour': utc_reset_hour,
          'cursor': cursor,
      }
      logging.info('params for next run: %s', params)
      fetch_task = taskqueue.Task(url='/report/fetch', params=params)
      fetch_task.add(queue_name='snippet-fetch-queue')


class SnippetMailWorker(webapp.RequestHandler):
  """Worker designed to mail a user their snippets."""

  # pylint: disable-msg=C6409
  def post(self):
    """Email this user their snippets."""
    email = self.request.get('email')
    user = self.request.get('user')
    datestamp = self.request.get('datestamp')
    snippets = self.request.get('snippets')
    if not email:
      logging.info('Missing email, quitting.'
                   'email: %s, user: %s, datestamp: %s, snippets: %s',
                   email, user, datestamp, snippets)
      return
    logging.info('Mailing snippets to %s...', email)

    # Email each user their snippets.
    subject = "%s's snippets since %s" % (user, datestamp)
    sender = 'snipper@google.com'
    body = 'Last week (%s)\n%s\n\n' % (datestamp, snippets)
    try:
      deferred.defer(mail.send_mail, sender=sender, to=email, subject=subject,
                     body=body)
    except DeadlineExceededError:
      logging.info('Deferred call to mail.send_mail timed out. Trying again.')
      # Create another deferred call, since mail.send tends to timeout.
      try:
        deferred.defer(mail.send_mail, sender=sender, to=email, subject=subject,
                       body=body)
      except DeadlineExceededError:
        logging.error('Deferred call to mail.send_mail timed out on 2nd try.')


application = webapp.WSGIApplication(
    [('/report/weekly', SnippetFetchWorker),
     ('/report/mail', SnippetMailWorker),
     ('/report/fetch', SnippetFetchWorker),
    ], debug=True)


def main():
  webapputil.run_wsgi_app(application)

if __name__ == '__main__':
  main()
