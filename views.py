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

"""Snipper is a Google snippet management tool."""

__author__ = 'erichiggins@gmail.com (Eric Higgins)'

import calendar
import datetime
import logging
import os
import urllib
import json  # pylint: disable-msg=C6204
os.environ['DJANGO_SETTINGS_MODULE'] = 'appengine_config'
from google.appengine import dist  # pylint: disable-msg=C6204
dist.use_library('django', '1.1')
from django.utils import simplejson  # pylint: disable-msg=C6204
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import ereporter
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import util as webapp_util
import models
import pytz
import util


ereporter.register_logger()


class PreferencesHandler(webapp.RequestHandler):
  """Handle the user preferences page."""

  @webapp_util.login_required
  # pylint: disable-msg=C6409
  def get(self):
    """Render the preferences page."""
    user = users.get_current_user()
    snipper_user = models.GetSnippetUser(user)
    errors = self.request.get('errors', '')
    logging.info(errors)
    errors = filter(None, errors.split(','))
    logging.info(errors)

    template_values = {
        'gaia': util.GetGaiaData(user),
        'user': user,
        'errors': errors,
        'snipper_user': snipper_user,
        'reset_days': calendar.day_name,
        'reset_hours': ([(0, '12 am')] +
                        [(x, '%s am' % x) for x in xrange(1, 12)] +
                        [(12, '12 pm')] +
                        [(x, '%s pm' % (x - 12)) for x in xrange(13, 24)]),
    }
    path = os.path.join(os.path.dirname(__file__), 'templates/preferences.html')
    rendered_page = template.render(path, template_values)
    self.response.headers['Expires'] = util.GetExpiryHeader(minutes=0)
    self.response.headers['Cache-Control'] = 'private, max-age=0'
    self.response.out.write(rendered_page)

  # pylint: disable-msg=C6409
  def post(self):
    """Save the user's preferences."""
    user = users.get_current_user()
    snipper_user = models.GetSnippetUser(user)
    logging.debug('Saving settings for %s', user)
    errors = []
    date_format = str(self.request.get('date_format', snipper_user.date_format))
    snippet_format = self.request.get('snippet_format',
                                      snipper_user.snippet_format)
    snipper_user.mail_snippets = bool(self.request.get('mail_snippets', False))
    snipper_user.send_confirm = bool(self.request.get('send_confirm', False))
    snipper_user.reset_day = int(self.request.get('reset_day',
                                                  snipper_user.reset_day))
    snipper_user.reset_hour = int(self.request.get('reset_hour',
                                                   snipper_user.reset_hour))
    timezone = self.request.get('timezone')
    try:
      assert pytz.timezone(timezone)
    except pytz.UnknownTimeZoneError:
      logging.exception('Invalid timezone: %s', timezone)
      errors.append('Invalid timezone: %s.' % timezone)
    else:
      snipper_user.timezone = timezone
      # Convert to UTC for storage.
      utc_reset = util.ResetDatetimeToUtc(snipper_user.reset_day,
                                          snipper_user.reset_hour,
                                          snipper_user.timezone)
      snipper_user.utc_reset_day = utc_reset.weekday()
      snipper_user.utc_reset_hour = utc_reset.hour
    try:
      assert datetime.datetime.now().strftime(date_format)
    except (ValueError, TypeError):
      errors.append('Invalid date format "%s".' % date_format)
      logging.exception('date_format "%s" failed validation.', date_format)
    else:
      snipper_user.date_format = date_format
    try:
      assert snippet_format % 'test snippet'
    except (ValueError, TypeError):
      errors.append('Invalid snippet format "%s".'  % snippet_format)
      logging.exception('snippet_format "%s" is invalid.', snippet_format)
    else:
      snipper_user.snippet_format = snippet_format
    logging.debug('date:%s, snip:%s, mail:%s, conf:%s, day:%s, hour:%s, tz:%s'
                  'utc_day:%s, utc_hour:%s',
                  snipper_user.date_format,
                  snipper_user.snippet_format,
                  snipper_user.mail_snippets,
                  snipper_user.send_confirm,
                  snipper_user.reset_day,
                  snipper_user.reset_hour,
                  snipper_user.timezone,
                  snipper_user.utc_reset_day,
                  snipper_user.utc_reset_hour)
    try:
      db.put(snipper_user)
    except (db.Timeout, db.InternalError):
      logging.exception('Could not save settings.')
      errors.append('Could not save settings.')
    else:
      memcache_key = 'SnippetUser-' + str(user)
      memcache.set(memcache_key, snipper_user)
    if errors:
      errors = urllib.quote_plus(','.join(errors))
      return self.redirect('/settings?errors=' + errors)
    # Drop the last two weeks from memcache.
    memcache.delete_multi(['snippets_%s_%d' % (str(user), x) for x in (0, 1)])
    self.redirect('/?msg=Settings+saved.')


class AddSnippet(webapp.RequestHandler):
  """Add new snippets to datastore."""

  def post(self):  # pylint: disable-msg=C6409
    """Add a snippet to the datastore for a user. Print 1 on success."""
    self.response.headers['Content-Type'] = 'application/json'
    user = users.get_current_user()
    snip = self.request.get('s', '')
    version = self.request.get('v', '')
    if not user:
      logging.debug('Could not get user information, bailing out. '
                    'Version: %s Snippet: %s', version, snip)
      self.response.out.write('0')
      return
    # Make sure the user has been added.
    assert models.GetSnippetUser(user)
    if not snip:
      logging.debug('Empty snippet.')
      self.response.out.write('0')
      return

    result = models.SaveSnippet(user, version, snip)
    self.response.out.write(int(result[0]))


class ViewSnippets(webapp.RequestHandler):
  """Return a users snippets."""

  @webapp_util.login_required
  def get(self):  # pylint: disable-msg=C6409
    """Print a users snippets."""
    try:
      offset = int(self.request.get('offset', default_value=0))
    except ValueError:
      offset = 0
    results = models.FetchSnippets(offset=offset)
    self.response.headers['Content-Type'] = 'application/json'
    snip = ''.join(s.Snippet for s in results)
    self.response.out.write(snip + '\n')


class JsonHandler(webapp.RequestHandler):
  """Handle JSON requests for the web front end."""

  @webapp_util.login_required
  def get(self):  # pylint: disable-msg=C6409
    """Return a users snippets for the requested timeframe in JSON format."""
    snipper_user = models.GetSnippetUser(users.get_current_user())
    tz = pytz.timezone(snipper_user.timezone)
    try:
      offset = int(self.request.get('offset', default_value=0))
    except ValueError:
      offset = 0
    results = models.FetchSnippets(offset=offset)
    self.response.headers['Content-Type'] = 'application/json'
    start_date = util.GetLastWeekDay(snipper_user.reset_day,
                                     offset,
                                     snipper_user.reset_hour,
                                     tz)
    end_date = util.GetNextWeekDay(snipper_user.reset_day,
                                   offset,
                                   snipper_user.reset_hour,
                                   tz)
    ret = {
        'snippets': [{'key': str(s.key()), 'text': s.Snippet} for s in results],
        'dates': {
            'from': start_date.strftime('%b %d'),
            'to': end_date.strftime('%b %d')
        }
    }
    self.response.out.write(simplejson.dumps(ret))


class StaticHandler(webapp.RequestHandler):
  """Render Django templates as static HTML.."""

  def get(self, filename):  # pylint: disable-msg=C6409
    user = users.get_current_user()
    template_values = {'gaia': util.GetGaiaData(user)}
    path = os.path.join(os.path.dirname(__file__), 'templates/', filename)
    rendered_page = template.render(path, template_values)
    self.response.headers['Expires'] = util.GetExpiryHeader()
    self.response.headers['Cache-Control'] = 'public, max-age=600'
    self.response.out.write(rendered_page)


class ErrorHandler(webapp.RequestHandler):
  """Error handler."""

  def get(self):  # pylint: disable-msg=C6409
    logging.error(self.request)
    return self.error(404)


class MainHandler(webapp.RequestHandler):
  """Main handler for Snipper."""

  @webapp_util.login_required
  def get(self):  # pylint: disable-msg=C6409
    """Render the Snipper page."""
    user = users.get_current_user()
    snipper_user = models.GetSnippetUser(user)
    tz = pytz.timezone(snipper_user.timezone)
    try:
      offset = int(self.request.get('offset', default_value=0))
    except ValueError:
      offset = 0
    results = models.FetchSnippets(offset=offset)
    snippets = [s.Snippet for s in results]
    template_values = {
        'gaia': util.GetGaiaData(user),
        'user': user,
        'reset_day': calendar.day_name[snipper_user.reset_day],
        'start': util.GetLastWeekDay(snipper_user.reset_day,
                                     hour=snipper_user.reset_hour,
                                     tz=tz),
        'end': util.GetNextWeekDay(snipper_user.reset_day,
                                   hour=snipper_user.reset_hour,
                                   tz=tz),
        'snippets': snippets,
        'offset': offset,
        'older': offset + 1,
        'msg': self.request.get('msg'),
    }
    if offset:
      template_values['newer'] = offset - 1
    else:
      template_values['newer'] = 0

    path = os.path.join(os.path.dirname(__file__), 'templates/index.html')
    rendered_page = template.render(path, template_values)
    self.response.headers['Expires'] = util.GetExpiryHeader(minutes=1)
    self.response.headers['Cache-Control'] = 'private, max-age=60'
    self.response.out.write(rendered_page)


application = webapp.WSGIApplication(
    [('/', MainHandler),
     ('/index.html', MainHandler),
     ('/view', ViewSnippets),
     ('/json', JsonHandler),
     ('/add', AddSnippet),
     (r'^/([a-zA-Z\d][\w\-]+\.html)$', StaticHandler),
     ('/_wave/.*', ErrorHandler),
     ('/settings', PreferencesHandler),
    ],
    debug=True)


def main():
  webapp_util.run_wsgi_app(application)

if __name__ == '__main__':
  main()
