#!/usr/bin/python2.4
# coding=UTF-8
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

"""Snipper URL mapping."""

__author__ = 'erichiggins@gmail.com (Eric Higgins)'

import sys
import appengine_config
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
import chat
import report
import settings
import views
import models
# Hack that prevents memcache from blowing up after the path change of models.
# TODO(erichiggins): Flush memcache on the server to fix this and remove hack.
sys.modules['models'] = models


url_mapping = [
    # views.py
    ('/', views.MainHandler),
    ('/index.html', views.MainHandler),
    ('/faq.html', views.FaqRedirect),
    ('/view', views.ViewSnippets),
    ('/json', views.JsonHandler),
    ('/add', views.AddSnippet),
    (r'^/([a-zA-Z\d][\w\-]+\.html)$', views.StaticHandler),
    ('/_wave/.*', views.ErrorHandler),
    ('/settings', views.PreferencesHandler),
    # chat.py
    ('/_ah/xmpp/message/', chat.XmppHandler),
    ('/_ah/xmpp/message/chat/', chat.XmppHandler),
    # report.py
    ('/report/weekly', report.SnippetFetchWorker),
    ('/report/mail', report.SnippetMailWorker),
    ('/report/fetch', report.SnippetFetchWorker),
]
application = webapp.WSGIApplication(url_mapping, debug=settings.DEBUG)


def main():
  util.run_wsgi_app(application)


if __name__ == '__main__':
  main()
