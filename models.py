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

import logging
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import db
import pytz
import util


class Snippet(db.Model):
  """Datastore model for storing snippet strings."""
  User = db.UserProperty(auto_current_user_add=True)
  Snippet = db.StringProperty(unicode, default=None, multiline=False)
  ExtensionVersion = db.StringProperty(unicode, default=None, multiline=False)
  DateStamp = db.DateTimeProperty(auto_now_add=True)


def SaveSnippet(user, version, snippet):
  """Save the snippet into the datastore.

  Args:
    user: User object.
    version: String detailing which interface version was used.
    snippet: Snippet string.

  Returns:
    Bool, Return message.
  """
  logging.debug('saving snippet for %s', user)
  try:
    query = Snippet(User=user, ExtensionVersion=version, Snippet=snippet)
  except db.BadValueError, err:
    logging.debug('Caught exception, bad value.')
    return False, err or 'Bad value given. 500 chars max.'
  try:
    db.put(query)
  except (db.Timeout, db.InternalError, db.BadValueError), err:
    logging.debug('Caught exception, trying again')
    return False, err or 'Snipper hit an error. 500 chars max.'

  logging.debug('worked')
  return True, ''


def FetchSnippets(user=None, offset=0, limit=1000):
  """Fetch the user's snippets.

  Args:
    user: User object to specify in the datastore query.
    offset: Number of weeks to offset (0= this week, 1=last week).
    limit: Number of snippets to return (max=1000).

  Returns:
    List of user's snippets.
  """
  if user is None:
    user = users.get_current_user()
  snipper_user = GetSnippetUser(user)
  day = snipper_user.reset_day
  hour = snipper_user.reset_hour
  tz = pytz.timezone(snipper_user.timezone)
  start_date = util.GetLastWeekDay(day, offset, hour, tz)
  end_date = util.GetNextWeekDay(day, offset, hour, tz)

  logging.info('FetchSnippets from %s to %s for %s',
               start_date, end_date, user)

  cachekey = 'snippets_%s_%d' % (str(user), offset)
  logging.info('Memcache key: %s', cachekey)
  cachetime = 1
  snippets = memcache.get(cachekey)
  if snippets is None:
    logging.debug('Memcache did not have snippets, fetching.')
    query = db.Query(Snippet).filter('User =', user)
    query.filter('DateStamp >=', start_date).filter('DateStamp <=', end_date)
    query.order('DateStamp')
    snippets = query.fetch(limit=limit)
    if not memcache.set(cachekey, snippets, cachetime):
      logging.debug('Memcache set failed for fetchSnippets')

  return snippets


class SnippetUser(db.Model):
  """Datastore model for Snipper user settings."""
  # The properties User, CreatedDateStamp and DateStamp do not conform to the
  # Python style guide, but can not be changed because of App Engine Datastore
  # limitations.
  User = db.UserProperty(auto_current_user_add=True)
  CreatedDateStamp = db.DateTimeProperty(auto_now_add=True)
  DateStamp = db.DateTimeProperty(auto_now=True)
  snippet_format = db.StringProperty(default='- %s')
  date_format = db.StringProperty(default='%Y-%m-%d')
  mail_snippets = db.BooleanProperty(default=True)
  send_confirm = db.BooleanProperty(default=True)
  cheeky_confirm = db.BooleanProperty(default=False)
  # Default reset is Monday (day=0) at 3pm (hour=15) America/Los_Angeles time.
  reset_day = db.IntegerProperty(default=0, choices=range(0, 7))
  reset_hour = db.IntegerProperty(default=15, choices=range(0, 24))
  timezone = db.StringProperty(default='America/Los_Angeles')
  # UTC day/hour from above, used for efficient cron/datastore queries.
  utc_reset_day = db.IntegerProperty(default=1, choices=range(0, 7))
  utc_reset_hour = db.IntegerProperty(default=3, choices=range(0, 24))


def GetSnippetUser(user=None):
  """Try to get the Snipper user from the datastore, create if not.

  Args:
    user: User object.

  Returns:
    SnippetUser object.
  """
  if user is None:
    user = users.get_current_user()
  logging.debug('GetSnippetUser call for %s', user)
  logging.debug('Trying memcache first...')
  memcache_key = 'SnippetUser-' + str(user)
  snippet_user = memcache.get(memcache_key)
  # Added a check for the timezone to ensure the SnipperUser version is updated.
  if snippet_user and snippet_user.timezone:
    logging.debug('Memcache worked, returning.')
    return snippet_user
  else:
    snippet_user = db.Query(SnippetUser).filter('User = ', user).get()
    if snippet_user is None:
      logging.info('Adding new Snipper user: %s', user)
      timezone = util.GetUserTimezone(user.nickname())
      snippet_user = SnippetUser()
      snippet_user.User = user  # pylint: disable-msg=C6409
      if timezone:
        snippet_user.timezone = timezone
      db.put(snippet_user)
    memcache.set(memcache_key, snippet_user)
    return snippet_user
