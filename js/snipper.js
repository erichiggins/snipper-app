/**
 * Copyright 2012 Google Inc. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 *     Unless required by applicable law or agreed to in writing, software
 *     distributed under the License is distributed on an "AS IS" BASIS,
 *     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *     See the License for the specific language governing permissions and
 *     limitations under the License.
 */
var snipper = snipper || {};

snipper.Snippets = function() {
  var ajax = XH_XmlHttpCreate();
  var urls = {fetch: '/json', add: '/add'};
  var dates = {};
  /**
   * Current week offset (0=this week, 1=last week, etc.).
   */
  var offset = 0;
  var snippets = {};
  /**
   * Map the UI elements.
   */
  var ui = {
    addForm: document.getElementById('addForm'),
    curdate: document.getElementById('date'),
    current: document.getElementById('current'),
    input: document.getElementById('s'),
    newer: document.getElementById('newer'),
    older: document.getElementById('older'),
    snippets: document.getElementById('snippetList')
  };

  /**
   * Load the snippets and dates from the JSON object, then refresh the UI.
   */
  var load = function(snippetObj) {
    dates[offset] = snippetObj.dates;
    snippets[offset] = [];
    for (var i = 0, len = snippetObj.snippets.length; i < len; i += 1) {
      snippets[offset].push(snippetObj.snippets[i].text);
    }
    refresh();
  };

  /**
   * Refresh the UI. Show/Hide date links, change the date, display the
   * snippets.
   */
  var refresh = function() {
    if (offset !== 0) {
      show('current');
      show('newer');
    } else {
      hide('current');
      hide('newer');
    }
    ui.snippets.disabled = false;
    ui.snippets.innerHTML = snippets[offset].join('\n');
    ui.curdate.innerHTML = dates[offset].from + ' to ' + dates[offset].to;
  };

  /**
   * Do an AJAX request to pull down the latest list of snippets.
   * Only do this once for previous week snippets, since they don't change.
   */
  var fetch = function() {
    // don't fetch if we already have them
    if (offset >= 0 && snippets[offset]) {
      refresh();
      return false;
    }
    ui.snippets.innerHTML = 'Loading...';
    ui.snippets.disabled = true;
    var url = urls.fetch + '?offset=' + offset;
    ajax.open('GET', url, true);
    ajax.send(null);
    return false;
  };

  /**
   * Decrease offset (forward in time) and refresh UI.
   */
  var newer = function() {
    if (offset > 0) {
      offset -= 1;
    }
    return fetch();
  };

  /**
   * Increase offset (backwards in time) and refresh UI.
   */
  var older = function() {
    offset += 1;
    return fetch();
  };

  /**
   * Offset to zero (current week) and refresh UI.
   */
  var current = function() {
    offset = 0;
    return fetch();
  };

  /**
   * Send the snippet via AJAX to the server, check the response, update UI.
   */
  var add = function() {
    var v = ui.addForm.elements['v'].value;
    var val = ui.input.value;

    if (!val.length || val == ui.input.defaultValue) {
      return false;
    }
    var data = '?v=' + encodeURIComponent(v) + '&s=' + encodeURIComponent(val);

    ui.input.value = '';
    var ajax = XH_XmlHttpCreate();
    var handler = function() {
        if (ajax.readyState === 4) {
          if (ajax.status === 200) {
            snippets[0].push(val);
            if (offset === 0) {
              refresh();
            }
          } else {
            ui.input.value = val;
          }
        }};

    XH_XmlHttpPOST(ajax, urls.add, data, handler);
    return false;
  };

  /**
   * Hide a mapped UI element.
   */
  var hide = function(key) {
    ui[key].style.display = 'none';
  };

  /**
   * Show a mapped UI element.
   */
  var show = function(key) {
    ui[key].style.display = 'inline';
  };

  /**
   * Initialize Snipper, creating event handlers.
   */
  var init = function() {
    var olderHandler = function() { return older(); };
    var newerHandler = function() { return newer(); };
    var currentHandler = function() { return current(); };
    var selectHandler = function() { this.select(); };
    var submitHandler = function() { return add(); };
    var inputFocusHandler = function() {
      if (ui.input.value == ui.input.defaultValue) {
        ui.input.value = '';
        ui.input.className = '';
      }
    };
    var inputBlurHandler = function() {
      if (!ui.input.value && ui.input.value != ui.input.defaultValue) {
        ui.input.value = ui.input.defaultValue;
        ui.input.className = 'default';
      }
    };

    ui.older.onclick = olderHandler;
    ui.newer.onclick = newerHandler;
    ui.current.onclick = currentHandler;
    try {
      // Disable autocomplete in Firefox
      ui.addForm.setAttribute('autocomplete', 'off');
    } catch (e) {}
    ui.addForm.onsubmit = submitHandler;
    ui.snippets.onfocus = selectHandler;
    ui.input.onfocus = inputFocusHandler;
    ui.input.onblur = inputBlurHandler;
    ui.input.focus();
    ajax.onreadystatechange = function() {
        if (ajax.readyState === 4) {
          var result = eval('(' + ajax.responseText + ')');
          load(result);
        }
      };
  }();

  /**
   * Return the public methods and properties.
   */
  return {
    'dates': dates,
    'snippets': snippets,
    'offset': offset,
    'add': add,
    'newer': newer,
    'older': older,
    'current': current
  };
}();

/**
 * Exports.
 */
window['snipper'] = snipper;
window['snipper']['Snippets'] = snipper.Snippets;
window['XH_XmlHttpCreate'] = XH_XmlHttpCreate;
