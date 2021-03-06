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

import json
import logging
import os
import signal

from lens.view import View
from lens.thread import Thread, ThreadManager

# GTK
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import WebKit2, Gtk, GObject



class ThreadManagerGtk(ThreadManager):
  def __init__(self, maxConcurrentThreads=10):
    ThreadManager.__init__(self, maxConcurrentThreads)

    # watch the queue for updates
    _fd = self.queue_in._reader.fileno()

    GObject.io_add_watch(_fd, GObject.IO_IN, self._on_cb)

  def _on_cb(self, fd, cond):
    while not self.queue_in.empty():
      data = self.queue_in.get()

      if data['name'] == '__completed':
        self._thread_completed(self.threads[data['uuid']]['t'])

      else:
        self.emit('__thread_%s_%s' % (data['uuid'], data['name']), self.threads[data['uuid']], *data['args'])

    return True


class _WebView(WebKit2.WebView):
  """
  """

  __gsignals__ = {
    'on-js': (GObject.SIGNAL_RUN_LAST, None, (GObject.TYPE_STRING,GObject.TYPE_PYOBJECT,))
  }

  def __init__(self, inspector=False):
    WebKit2.WebView.__init__(self)

    # register signals
    self.connect('decide-policy', self._decide_policy_cb)
    self.connect('load-changed', self._load_changed_cb)
    self.connect('notify::title', self._title_changed_cb)

    #: need access to the context menu to inspect the app
    if not inspector:
      self.connect('context-menu', self._context_menu_cb)

    self.l_uri = None

    enable_settings = ['enable-accelerated-2d-canvas', 'enable-smooth-scrolling', 'javascript-can-access-clipboard']

    for setting in enable_settings:
      try:
        self.get_settings().set_property(setting, True)
      except:
        pass

    if inspector:
      try:
        self.get_settings().set_property('enable-developer-extras', True)
      except:
        pass

  def _context_menu_cb(self, view, context_menu, event, hit_test_result):
    return True

  def _decide_policy_cb(self, view, decision, decision_type):
    if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:

      # grab the requested URI
      uri = decision.get_request().get_uri()

  def _load_changed_cb(self, view, event):
    pass

  def _title_changed_cb(self, view, event):
    _in = view.get_title()

    # check for "_BR::" leader to determine we're crossing
    # the python/JS bridge
    if _in is None or not _in.startswith('_BR::'):
      return

    try:
      _in = json.loads(_in[5:])

      _name = _in.setdefault('name', '')
      _args = _in.setdefault('args', [])

      # emit our python/js bridge signal
      self.emit('on-js', _name, _args)

    except:
      pass



class ViewGtk(View):


  def __init__(self, name="MyLensApp", width=640, height=480, inspector=False, *args, **kwargs):
    View.__init__(self, name=name, width=width, height=height, *args, **kwargs)
    # prepare Gtk dbus mainloop
    DBusGMainLoop(set_as_default=True)

    self._app_loaded = False

    self._logger = logging.getLogger('Lens.ViewGtk')
    self._manager = ThreadManagerGtk()
    self._uri_lens_base = None

    self._inspector = inspector
    self._build_app()

  def _build_app(self):
    # build window and webkit container
    self._window = w = Gtk.Window()
    self._lensview = lv = _WebView(inspector=self._inspector)

    # add lensview to the parent window
    w.add(lv)

    # connect to Gtk signals
    lv.connect('on-js', self._on_js)
    lv.connect('load-changed', self._load_change_cb)
    w.connect('delete-event', self._delete_event_cb)

    # connect to Lens signals
    self.on('__close_app', self._close_cb)

    # center on screen
    w.set_position(Gtk.WindowPosition.CENTER)

    self.set_title(self._app_name)
    self.set_size(self._app_width, self._app_height)

  def _close_cb(self, *args):
    self.emit('app.close')
    Gtk.main_quit(*args)

  def _delete_event_cb(self, *args):
    self.emit('__close_app', *args)

  def _load_change_cb(self, view, event):
    # show window once some page has loaded
    if( event == WebKit2.LoadEvent.FINISHED ):
      self._window.show_all()

      if not self._app_loaded:
        self._app_loaded = True
        self.emit('app.loaded')

  def _run(self):
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    Gtk.main()

  def emit_js(self, name, *args):
    self._lensview.run_javascript('var _rs = angular.element(document).scope(); _rs.safeApply(function(){_rs.$broadcast.apply(_rs,%s)});' % json.dumps([name] + list(args)), None, None, None)

  def load_uri(self, uri):
    # TODO: we require webkitgtk3 2.2.7 or later
    #
    # FIXME
    # improve resource handling of lens:// schemas by intercepting resources
    # via WebKitWebPage (extensions) send-request(). Not yet exposed in python
    #
    # for now we emulate the effect with a replace
    uri_base = os.path.dirname(uri) + '/'
    html = open(uri.replace('file://',''), 'r').read()
    html = html.replace('lens://', self._uri_lens_base)
    html = html.replace('app://', uri_base)

    self._lensview.load_html(html, uri_base)

  def set_size(self, width, height):
    self._window.set_size_request(width, height)

  def set_title(self, title):
    self._window.set_title(title)
    self._window.set_wmclass(title, title)

