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

"""Snipper/App Engine config file.

This contains the global configuration options for the Snipper app.
Usage of this file is described here:
  http://code.google.com/appengine/docs/python/tools/appstats.html
"""

__author__ = 'erichiggins@gmail.com (Eric Higgins)'

from google.appengine import dist
dist.use_library('django', '1.1')


MIDDLEWARE_CLASSES = (
    'google.appengine.ext.appstats.recording.AppStatsDjangoMiddleware',
)


def webapp_add_wsgi_middleware(app): # pylint: disable-msg=C6409
  from google.appengine.ext.appstats import recording
  return recording.appstats_wsgi_middleware(app)
