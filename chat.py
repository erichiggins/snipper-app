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
from google.appengine.api import capabilities
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.api import xmpp
from google.appengine.ext import deferred
from google.appengine.ext import ereporter
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
import models
import pytz


ereporter.register_logger()

_HELP_TEMPLATE = ('Snipper Help\n'
                  'Hi %(user)s, just send me your snippets!\n'
                  'Commands:\n'
                  '*help*: Print this text.\n'
                  '*last*: Print the last successfully received snippet.\n'
                  '*status*: Print the status of Snipper.\n'
                  '*whoami*: See who you are..\n'
                  '*emailme*: Get the link to send snippet emails.\n'
                  '\nView your snippets at http://go/snipper'
                 )
_STATUS_TEMPLATE = ('Snipper status: %(status)s\n'
                    '%(help)s')
_SUCCESS_MSGS = [
    ':)',
    'Rock on!',
    'Great work!',
    'You must be feeling lucky!',
    'Thanks!',
    'Keep up the good work!',
    'Awesome!',
    '=D',
    'Radical!',
    'Excellent!',
    'Way to go!',
    'Woohoo!',
    'Nice job!',
]
_CHEEKY_MSGS = [
    ':\\',
    'Is that the best you can do?',
    'Really?',
    'Meets expectations.',
    'Sigh...',
    'I think you do better.',
    ':|',
    'Um, okay.',
    'Get back to work.',
    'Slacker!',
    'Yikes.',
    'Oh bother.',
]


def GetHelp(user):
  """Return some help text to send back by chat."""
  return _HELP_TEMPLATE % {'user': user}


def GetLastSnippet(user):
  """Return the last successfully recorded snippet for the user."""
  last = models.Snippet.gql('WHERE User=:1 ORDER BY DateStamp DESC',
                            user).get()
  if last:
    return last.Snippet
  else:
    return 'Sorry, I could not find any previous snippets for you.'


def GetStatus(user):
  """Return the status of Snipper, according to the datastore write."""
  status = 'OK'
  help_msg = 'Snipper should be working properly.'
  datastore_write = capabilities.CapabilitySet('datastore_v3',
                                               capabilities=['write'])
  if not datastore_write.is_enabled():
    status = 'Read only'
    help_msg = 'App Engine is down for maintenance, please try again later.'
  return _STATUS_TEMPLATE % {'help': help_msg, 'status': status, 'user': user}


def GetUserInfo(user):
  """Return the user's information."""
  snipper_user = models.GetSnippetUser(user)
  return '%s , %s' % (user.email(), snipper_user.timezone)


def SendUserSnippets(user):
  """Send the user their snippet email."""
  # TODO(eric): Update URL to public version.
  url = 'http://appspot.com'
  return 'To email your snippets to %s, visit: %s' % (user.email(), url)


_CHAT_COMMANDS = {
    'help': GetHelp,
    'last': GetLastSnippet,
    'status': GetStatus,
    'whoami': GetUserInfo,
    'emailme': SendUserSnippets,
}


def GetNextSuccessMsg(username=None, cheeky=False):
  """Return the next success message."""
  key = 'next_success_msg_index'
  if cheeky:
    messages = _CHEEKY_MSGS
  else:
    messages = _SUCCESS_MSGS
  try:
    index = int(memcache.get(key, namespace=username))
  except TypeError:
    index = 0
  if index + 1 >= len(messages):
    memcache.set(key, 0, namespace=username)  # Reached the end, reset to 0.
  else:
    memcache.incr(key, initial_value=0, namespace=username)  # Increment by 1.

  return messages[index]


class XmppHandler(webapp.RequestHandler):
  """Handle XMPP (Google Talk) requests."""

  def Reply(self, user, message):
    try:
      xmpp.send_message(user, message)
    except xmpp.Error, xmpp.NoBodyError:
      logging.exception('Caught error when trying to send.')
      # Create a deferred call.
      deferred.defer(xmpp.send_message, jids=user, body=message)

  # pylint: disable-msg=C6409
  def post(self):
    """Get a chat, add to datastore."""
    err_msg = ':( %s'
    msg_from = self.request.get('from', '')
    msg_body = self.request.get('body', '').strip()
    if msg_body:
      logging.debug('Got a chat message from %s: "%s"', msg_from, msg_body)

      # Grab the username by removing the resource (if present) from the JID
      user_address = msg_from.split('/', 1)[0]

      # Try to create a snippetUser object.
      user = users.User(user_address)
      snipper_user = models.GetSnippetUser(user)
      if not snipper_user:
        logging.debug('Could not create a User object.')
        self.Reply(msg_from, err_msg)
        return

      # Disable the confirmation message for users that don't want it.
      if snipper_user.send_confirm is False:
        success_msg = ''
      else:
        # Check for April 1st, display cheeky messages :).
        now = datetime.datetime.now(pytz.timezone(snipper_user.timezone))
        cheeky = False
        if snipper_user.cheeky_confirm or (now.month == 4 and now.day == 1):
          cheeky = True
        success_msg = GetNextSuccessMsg(user.nickname(), cheeky)

      # Handle commands sent by chat.
      cmd = msg_body.lower()
      if cmd in _CHAT_COMMANDS:
        replies = _CHAT_COMMANDS[cmd](user)
        # Send the replies back to the user then quit.
        self.Reply(msg_from, replies)
        return

      # Convert multi-line snippets into a list.
      snippets = msg_body.splitlines()
      # Try to save each snippet, and store the result in the list.
      results, errors = zip(*[models.SaveSnippet(user, 'xmpp', s)
                              for s in snippets])

      if False not in results:
        message = success_msg
      else:
        message = err_msg % filter(None, errors)[0]  # Return the first error.
        logging.debug('%s said "%s"', msg_from, msg_body)

      if message:
        self.Reply(msg_from, message)


application = webapp.WSGIApplication([('/_ah/xmpp/message/', XmppHandler),
                                      ('/_ah/xmpp/message/chat/', XmppHandler)],
                                     debug=True)


def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
