#!/usr/bin/python2
#
# Copyright 2012-2014 "Korora Project" <dev@kororaproject.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the temms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import os
import pprint
import random
import time

from lens.app import App
from lens.thread import Thread

class LongTask(Thread):
  def __init__(self):
    Thread.__init__(self, daemon=True)

  def run(self):
    delta = random.uniform(0.05, 0.5)

    self.emit('started', self.uuid, time.time())

    for i in range(100):
      time.sleep(delta)
      self.emit('progress', self.uuid, i)

    self.emit('complete', self.uuid, time.time())



app = App(name="Lens. Threads", inspector=True)

# load the app entry page
app.namespaces.append('./sample-data')
app.load_ui('app-threads.html')

@app.connect('close')
def _close_app_cb(*args):
  app.close()

@app.connect('get-hostname')
def _get_hostname_cb(*args):
  app.emit('update-config', os.uname()[1])

@app.connect('update-hostname')
def _update_hostname_cb(message):
  pp = pprint.PrettyPrinter(indent=2)
  pp.pprint(message)

@app.connect('start-long-task')
def _long_task_cb():
  t = LongTask()
  app.threads.add(t)
  app.threads.on(t, 'progress', _longtask_progress_cb)
  app.threads.on(t, 'complete', _longtask_complete_cb)

def _longtask_progress_cb(thread, *args):
  app.emit('long-task-progress', *args)

def _longtask_complete_cb(thread, *args):
  app.emit('long-task-complete', *args)



app.start()

