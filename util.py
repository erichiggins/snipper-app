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

import datetime
import logging
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.api import users
from google.appengine.ext import ereporter
import pytz


ereporter.register_logger()
DEFAULT_TZ = 'America/Los_Angeles'
PACIFIC_TZINFO = pytz.timezone(DEFAULT_TZ)


def ResetDatetimeToUtc(reset_day, reset_hour, tzname):
  """Returns the user's reset day and hour in UTC time."""
  tz = pytz.timezone(tzname)
  return GetLastWeekDay(reset_day, 0, reset_hour, tz).astimezone(pytz.utc)


def GetUserTimezone(username):
  """Returns the timezone string of the given user."""
  # TODO(erichiggins): Implement orginfo, no tz support yet.
  # https://sites.google.com/a/google.com/orginfo_docs/
  tz = DEFAULT_TZ
  return tz


def GetExpiryHeader(days=0, hours=0, minutes=10):
  """Returns a date string formatted for the Expires HTTP header."""
  tz = pytz.timezone('GMT')
  now = datetime.datetime.now(tz).replace(second=0, microsecond=0)
  expire = now + datetime.timedelta(days=days, hours=hours, minutes=minutes)
  return expire.strftime('%a, %d %b %Y %H:%M:%S %Z')


def GetGaiaData(user):
  """Generate the links for the GAIA bar, if any, for the current user."""
  left = ['<a href="/">Snipper</a>']
  if user is None:
    return {'left_links': '\n'.join(left),
            'right_links': '<a href="%s">Sign in</a>' % (
                users.create_login_url('/'))}

  if users.is_current_user_admin():
    left.append('<a href="/admin/">Admin</a>')
    left.append('<a href="http://admin-console.prom.corp.google.com/logs?'
                'app_id=snipper&amp;logs_form=1&amp;severity_level=0#"'
                ' blank="_target">Logs</a>')
  right = ['<strong>%s</strong>' % user.email(),
           '<a href="/settings">Settings</a>',
           '<a href="%s">Sign out</a>' % (
               users.create_logout_url('/'))]
  return {'left_links': '\n'.join(left),
          'right_links': ' <span>|</span>\n'.join(right)}


def GetResetDate(weekday, hour=15, tz=PACIFIC_TZINFO, start=None):
  """Returns the datetime for the reset during the current week.

  Args:
    weekday: Day of the week as an integer (0=Sunday, 6=Saturday).
    hour: Hour in a 24-hour format integer.
    tz: Timezone of the user to use when creating the datetime object.
    start: Datetime to use as the starting point. Current date used if None.

  Returns:
    Datetime of the current weekly reset.
  """
  if not start:
    start = datetime.datetime.now(tz)
  reset = start.replace(hour=hour,
                        minute=0,
                        second=0,
                        microsecond=0)
  return reset + datetime.timedelta(days=(weekday - reset.weekday()))


def GetLastWeekDay(weekday, offset=0, hour=15, tz=PACIFIC_TZINFO, start=None):
  """Return the datetime for the previous weekday, such as last Monday.

  This is used to define the boundary for fetching a user's snippets within
  a given timeframe.

  Args:
    weekday: Day of the week as an integer (0=Sunday, 6=Saturday).
    offset: Number of weeks to offset the datetime (0=current, 1=last week).
    hour: Hour in a 24-hour format integer.
    tz: Timezone of the user to use when creating the datetime object.
    start: Datetime to use as the starting point. Current date used if None.

  Returns:
    Datetime representing the previous reset datetime.
  """
  if offset < 0:
    offset = 0
  weeks = offset * 7
  if not start:
    start = datetime.datetime.now(tz)
  reset = GetResetDate(weekday=weekday, hour=hour, tz=tz)
  logging.debug('start: %s , reset: %s', start, reset)

  if reset > start:
    reset -= datetime.timedelta(days=7)
  return reset - datetime.timedelta(days=weeks)


def GetNextWeekDay(weekday, offset=0, hour=15, tz=PACIFIC_TZINFO, start=None):
  """Return the datetime for the next weekday, such as next Monday.

  This is used to define the boundary for fetching a user's snippets within
  a given timeframe.

  Args:
    weekday: Day of the week as an integer (0=Sunday, 6=Saturday).
    offset: Number of weeks to offset the datetime (0=current, 1=last week).
    hour: Hour in a 24-hour format integer.
    tz: Timezone of the user to use when creating the datetime object.
    start: Datetime to use as the starting point. Current date used if None.

  Returns:
    Datetime representing the last, or most current, reset datetime.
  """
  if offset < 0:
    offset = 0
  weeks = offset * 7
  if not start:
    start = datetime.datetime.now(tz)
  reset = GetResetDate(weekday=weekday, hour=hour, tz=tz)
  logging.debug('start: %s , reset: %s', start, reset)

  if start > reset:
    reset += datetime.timedelta(days=7)
  return reset - datetime.timedelta(days=weeks)
