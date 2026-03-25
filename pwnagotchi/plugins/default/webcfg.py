import logging
import json
import toml
import threading  # FIX B5: replaced _thread with threading
import pwnagotchi
from pwnagotchi import restart, plugins
from pwnagotchi.utils import save_config, merge_config
from flask import abort
from flask import render_template_string

INDEX = """
{% extends "base.html" %}
{% set active_page = "plugins" %}
{% block title %}
    Webcfg
{% endblock %}

{% block meta %}
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, user-scalable=0" />
{% endblock %}{% block styles %}
{{ super() }}
<style>
    /* Webcfg-specific styles - plugin header */
    .webcfg-header {
        margin-bottom: 2rem;
        padding: 1.5rem 0;
        border-bottom: 1px solid var(--border-color);
    }

    /* Search/Control Bar */
    #divTop {
        position: -webkit-sticky;
        position: sticky;
        top: 0;
        display: flex;
        gap: 0.5rem;
        align-items: center;
        width: 100%;
        padding: 1rem;
        margin-bottom: 1.5rem;
        font-size: 0.95rem;
        background-color: var(--card-bg);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        z-index: 100;
    }

    #searchText {
        flex: 1;
        min-width: 200px;
    }

    /* Select Box for Add Type */
    #selAddType {
        min-width: 120px;
        cursor: pointer;
    }

    /* Wrapper spans */
    #divTop > span {
        display: flex;
        align-items: center;
    }

    /* Table Container */
    .table-container {
        background-color: var(--card-bg);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        overflow: hidden;
        box-shadow: var(--shadow-md);
        margin-bottom: 2rem;
    }

    table {
        table-layout: auto;
        width: 100%;
        border-collapse: collapse;
        background-color: var(--card-bg);
    }

    thead {
        background-color: var(--card-bg);
    }

    th {
        padding: 14px 16px;
        text-align: left;
        color: var(--accent);
        font-weight: 600;
        font-family: var(--font-pixel);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-size: 0.85rem;
        border-bottom: 2px solid var(--border-color);
    }

    td {
        padding: 12px 16px;
        text-align: left;
        border-bottom: 1px solid var(--border-color);
        color: var(--text-body);
        font-size: 0.9rem;
    }

    tbody tr:hover {
        background-color: rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.05);
        transition: background-color 0.2s ease;
    }

    tbody tr:last-child td {
        border-bottom: none;
    }

    /* Remove Button Column */
    td:nth-child(1) {
        width: 50px;
        padding: 12px 8px;
        text-align: center;
    }

    td:nth-child(1) .del_btn_wrapper {
        display: flex;
        justify-content: center;
    }

    /* Remove Button - Compact Icon Style */
    .remove {
        background-color: var(--danger);
        color: transparent;
        border: none;
        padding: 6px 6px;
        border-radius: 4px;
        font-size: 0.7rem;
        font-family: var(--font-pixel);
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 1px 4px rgba(255, 85, 85, 0.2);
        white-space: nowrap;
        letter-spacing: 0px;
        min-width: 32px;
        min-height: 32px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ffffff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='3 6 5 6 21 6'%3E%3C/polyline%3E%3Cpath d='M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2'%3E%3C/path%3E%3Cline x1='10' y1='11' x2='10' y2='17'%3E%3C/line%3E%3Cline x1='14' y1='11' x2='14' y2='17'%3E%3C/line%3E%3C/svg%3E");
        background-repeat: no-repeat;
        background-position: center;
        background-size: 18px;
    }

    .remove:hover {
        background-color: var(--danger-hover);
        box-shadow: 0 2px 6px rgba(255, 85, 85, 0.3);
        transform: scale(1.05);
    }

    .remove:active {
        transform: scale(0.95);
    }

    /* Save Button Group */
    #divSaveTop {
        position: -webkit-sticky;
        position: sticky;
        bottom: 0;
        display: flex;
        gap: 1rem;
        padding: 1rem;
        background-color: var(--card-bg);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        flex-wrap: wrap;
        z-index: 100;
        margin-top: 2rem;
    }

    #divSaveTop .btn {
        flex: 1;
        min-width: 150px;
    }

    /* Responsive Design */
    @media screen and (max-width: 768px) {
        #divTop {
            flex-direction: column;
            align-items: stretch;
        }

        #searchText {
            min-width: 100%;
        }

        th, td {
            padding: 10px 12px;
            font-size: 0.85rem;
        }

        td:nth-child(1) {
            width: 50px;
            padding: 10px 4px;
        }

        .remove {
            min-width: 30px;
            min-height: 30px;
            padding: 5px 5px;
        }

        #divSaveTop {
            flex-direction: column;
            gap: 0.75rem;
        }
    }

    @media screen and (max-width: 480px) {
        #divTop {
            padding: 0.75rem;
            margin-bottom: 1rem;
        }

        th, td {
            padding: 8px 10px;
            font-size: 0.8rem;
        }

        th {
            font-size: 0.75rem;
        }

        td:nth-child(1) {
            width: 50px;
            padding: 8px 4px;
        }

        .remove {
            min-width: 28px;
            min-height: 28px;
            padding: 4px 4px;
        }

        .table-container {
            margin-bottom: 2rem;
        }

        #divSaveTop {
            flex-direction: column;
            gap: 0.75rem;
            margin-bottom: 70px;
        }

        /* Mobile table display */
        table, tr, td {
            padding: 0;
            border: none;
        }

        table {
            border: none;
        }

        tr:first-child, thead, th {
            display: none;
            border: none;
        }

        tr {
            float: left;
            width: 100%;
            margin-bottom: 0.75rem;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            background-color: var(--card-bg);
            padding: 0.75rem;
        }

        td {
            float: left;
            width: 100%;
            padding: 0.5rem 0;
            margin-bottom: 0.25rem;
            border: none;
        }

        td::before {
            content: attr(data-label);
            display: block;
            color: var(--accent);
            font-weight: 600;
            font-family: var(--font-pixel);
            font-size: 0.8rem;
            text-transform: uppercase;
            margin-bottom: 0.25rem;
            letter-spacing: 0.5px;
        }

        td[data-label=""] {
            padding: 0 !important;
            margin-bottom: 0 !important;
        }

        td[data-label=""] .del_btn_wrapper {
            text-align: right;
            margin-bottom: 0.75rem;
        }
    }
</style>
{% endblock %}

{% block content %}
    <div class="webcfg-header">
        <h2>Configuration Manager</h2>
        <p>Edit your Pwnagotchi configuration settings</p>
    </div>

    <div id="divTop">
        <input type="text" id="searchText" placeholder="Search for options ..." title="Type an option name">
        <span><select id="selAddType"><option value="text">Text</option><option value="number">Number</option></select></span>
        <span><button class="btn primary" type="button" onclick="addOption()">+</button></span>
    </div>
    
    <div class="table-container" id="content"></div>

    <div id="divSaveTop">
        <button class="btn primary" type="button" onclick="saveConfig()">Save and restart</button>
        <button class="btn danger" type="button" onclick="saveConfigNoRestart()">Merge and Save (CAUTION)</button>
    </div>
{% endblock %}

{% block script %}
        function addOption() {
          var input, table, tr, td, divDelBtn, btnDel, selType, selTypeVal;
          input = document.getElementById("searchText");
          inputVal = input.value;
          selType = document.getElementById("selAddType");
          selTypeVal = selType.options[selType.selectedIndex].value;
          table = document.getElementById("tableOptions");
          if (table) {
            tr = table.insertRow();
            // del button
            divDelBtn = document.createElement("div");
            divDelBtn.className = "del_btn_wrapper";
            td = document.createElement("td");
            td.setAttribute("data-label", "");
            btnDel = document.createElement("Button");
            btnDel.innerHTML = "";
            btnDel.onclick = function(){ delRow(this);};
            btnDel.className = "remove";
            divDelBtn.appendChild(btnDel);
            td.appendChild(divDelBtn);
            tr.appendChild(td);
            // option
            td = document.createElement("td");
            td.setAttribute("data-label", "Option");
            td.innerHTML = inputVal;
            tr.appendChild(td);
            // value
            td = document.createElement("td");
            td.setAttribute("data-label", "Value");
            input = document.createElement("input");
            input.type = selTypeVal;
            input.value = "";
            td.appendChild(input);
            tr.appendChild(td);

            input.value = "";
          }
        }

        function saveConfig(){
            // get table
            var table = document.getElementById("tableOptions");
            if (table) {
                var json = tableToJson(table);
                sendJSON("webcfg/save-config", json, function(response) {
                    if (response) {
                        if (response.status == "200") {
                            alert("Config got updated");
                        } else {
                            alert("Error while updating the config (err-code: " + response.status + ")");
                        }
                    }
                });
            }
        }

        function saveConfigNoRestart(){
            // get table
            var table = document.getElementById("tableOptions");
            if (table) {
                var json = tableToJson(table);
                sendJSON("webcfg/merge-save-config", json, function(response) {
                    if (response) {
                        if (response.status == "200") {
                            alert("Config got updated");
                        } else {
                            alert("Error while updating the config (err-code: " + response.status + ")");
                        }
                    }
                });
            }
        }

        var searchInput = document.getElementById("searchText");
        searchInput.onkeyup = function() {
            var filter, table, tr, td, i, txtValue;
            filter = searchInput.value.toUpperCase();
            table = document.getElementById("tableOptions");
            if (table) {
                tr = table.getElementsByTagName("tr");

                for (i = 0; i < tr.length; i++) {
                    td = tr[i].getElementsByTagName("td")[1];
                    if (td) {
                        txtValue = td.textContent || td.innerText;
                        if (txtValue.toUpperCase().indexOf(filter) > -1) {
                            tr[i].style.display = "";
                        }else{
                            tr[i].style.display = "none";
                        }
                    }
                }
            }
        }

        function sendJSON(url, data, callback) {
          var xobj = new XMLHttpRequest();
          var csrf = "{{ csrf_token() }}";
          xobj.open('POST', url);
          xobj.setRequestHeader("Content-Type", "application/json");
          xobj.setRequestHeader('x-csrf-token', csrf);
          xobj.onreadystatechange = function () {
                if (xobj.readyState == 4) {
                  callback(xobj);
                }
          };
          xobj.send(JSON.stringify(data));
        }

        function loadJSON(url, callback) {
          var xobj = new XMLHttpRequest();
          xobj.overrideMimeType("application/json");
          xobj.open('GET', url, true);
          xobj.onreadystatechange = function () {
                if (xobj.readyState == 4 && xobj.status == "200") {
                  callback(JSON.parse(xobj.responseText));
                }
          };
          xobj.send(null);
        }

        // https://stackoverflow.com/questions/19098797/fastest-way-to-flatten-un-flatten-nested-json-objects
        function unFlattenJson(data) {
            "use strict";
            if (Object(data) !== data || Array.isArray(data))
                return data;
            var result = {}, cur, prop, idx, last, temp, inarray;
            for(var p in data) {
                cur = result, prop = "", last = 0, inarray = false;
                do {
                    idx = p.indexOf(".", last);
                    temp = p.substring(last, idx !== -1 ? idx : undefined);
                    inarray = temp.startsWith('#') && !isNaN(parseInt(temp.substring(1)))
                    cur = cur[prop] || (cur[prop] = (inarray ? [] : {}));
                    if (inarray){
                        prop = temp.substring(1);
                    }else{
                        prop = temp;
                    }
                    last = idx + 1;
                } while(idx >= 0);
                cur[prop] = data[p];
            }
            return result[""];
        }

        function flattenJson(data) {
            var result = {};
            function recurse (cur, prop) {
                if (Object(cur) !== cur) {
                    result[prop] = cur;
                } else if (Array.isArray(cur)) {
                     for(var i=0, l=cur.length; i<l; i++)
                         recurse(cur[i], prop ? prop+".#"+i : ""+i);
                    if (l == 0)
                        result[prop] = [];
                } else {
                    var isEmpty = true;
                    for (var p in cur) {
                        isEmpty = false;
                        recurse(cur[p], prop ? prop+"."+p : p);
                    }
                    if (isEmpty)
                        result[prop] = {};
                }
            }
            recurse(data, "");
            return result;
        }

        function delRow(btn) {
            var tr = btn.parentNode.parentNode.parentNode;
            tr.parentNode.removeChild(tr);
        }

        function jsonToTable(json) {
            var table = document.createElement("table");
            table.id = "tableOptions";

            // create header
            var tr = table.insertRow();
            var thDel = document.createElement("th");
            thDel.innerHTML = "";
            var thOpt = document.createElement("th");
            thOpt.innerHTML = "Option";
            var thVal = document.createElement("th");
            thVal.innerHTML = "Value";
            tr.appendChild(thDel);
            tr.appendChild(thOpt);
            tr.appendChild(thVal);

            var td, divDelBtn, btnDel;
            // iterate over keys
            Object.keys(json).forEach(function(key) {
                tr = table.insertRow();
                // del button
                divDelBtn = document.createElement("div");
                divDelBtn.className = "del_btn_wrapper";
                td = document.createElement("td");
                td.setAttribute("data-label", "");
                btnDel = document.createElement("Button");
                btnDel.innerHTML = "";
                btnDel.onclick = function(){ delRow(this);};
                btnDel.className = "remove";
                divDelBtn.appendChild(btnDel);
                td.appendChild(divDelBtn);
                tr.appendChild(td);
                // option
                td = document.createElement("td");
                td.setAttribute("data-label", "Option");
                td.innerHTML = key;
                tr.appendChild(td);
                // value
                td = document.createElement("td");
                td.setAttribute("data-label", "Value");
                if(typeof(json[key])==='boolean'){
                    input = document.createElement("select");
                    input.setAttribute("id", "boolSelect");
                    tvalue = document.createElement("option");
                    tvalue.setAttribute("value", "true");
                    ttext = document.createTextNode("True")
                    tvalue.appendChild(ttext);
                    fvalue = document.createElement("option");
                    fvalue.setAttribute("value", "false");
                    ftext = document.createTextNode("False");
                    fvalue.appendChild(ftext);
                    input.appendChild(tvalue);
                    input.appendChild(fvalue);
                    input.value = json[key];
                    document.body.appendChild(input);
                    td.appendChild(input);
                    tr.appendChild(td);
                } else {
                    input = document.createElement("input");
                    if(Array.isArray(json[key])) {
                        input.type = 'text';
                        input.value = '[]';
                    }else{
                        var valType = typeof(json[key]);
                        input.type = valType === 'string' ? 'text' : valType;
                        input.value = json[key];
                    }
                    td.appendChild(input);
                    tr.appendChild(td);
                }
            });

            return table;
        }

        function tableToJson(table) {
            var rows = table.getElementsByTagName("tr");
            var i, td, key, value;
            var json = {};

            for (i = 0; i < rows.length; i++) {
                td = rows[i].getElementsByTagName("td");
                if (td.length == 3) {
                    // td[0] = del button
                    key = td[1].textContent || td[1].innerText;
                    var input = td[2].getElementsByTagName("input");
                    var select = td[2].getElementsByTagName("select");
                    if (input && input != undefined && input.length > 0 ) {
                        if (input[0].type == "text") {
                            if (input[0].value.startsWith("[") && input[0].value.endsWith("]")) {
                                json[key] = JSON.parse(input[0].value);
                            }else{
                                json[key] = input[0].value;
                            }
                        }else if (input[0].type == "number") {
                            json[key] = Number(input[0].value);
                        }
                    } else if(select && select != undefined && select.length > 0) {
                        var myValue = select[0].options[select[0].selectedIndex].value;
                        json[key] = myValue === 'true';
                    }
                }
            }
            return unFlattenJson(json);
        }

        loadJSON("webcfg/get-config", function(response) {
            var flat_json = flattenJson(response);
            var table = jsonToTable(flat_json);
            var divContent = document.getElementById("content");
            divContent.innerHTML = "";
            divContent.appendChild(table);
        });
{% endblock %}
"""


def serializer(obj):
    if isinstance(obj, set):
        return list(obj)
    raise TypeError


class WebConfig(plugins.Plugin):
    __author__ = "33197631+dadav@users.noreply.github.com modified by wsvdmeer"
    __version__ = "1.0.0"
    __license__ = "GPL3"
    __description__ = "This plugin allows the user to make runtime changes."

    def __init__(self):
        self.ready = False
        self.mode = "MANU"
        self._agent = None

    def on_config_changed(self, config):
        self.config = config
        self.ready = True

    def on_ready(self, agent):
        self._agent = agent
        self.mode = "MANU" if agent.mode == "manual" else "AUTO"

    def on_internet_available(self, agent):
        self._agent = agent
        self.mode = "MANU" if agent.mode == "manual" else "AUTO"

    def on_loaded(self):
        """
        Gets called when the plugin gets loaded
        """
        logging.info("webcfg: Plugin loaded.")

    def on_webhook(self, path, request):
        """
        Serves the current configuration
        """
        if not self.ready:
            return "Plugin not ready"

        if request.method == "GET":
            if path == "/" or not path:
                return render_template_string(INDEX)
            elif path == "get-config":
                # send configuration
                return json.dumps(self.config, default=serializer)
            else:
                abort(404)
        elif request.method == "POST":
            if path == "save-config":
                try:
                    save_config(request.get_json(), '/etc/pwnagotchi/config.toml')  # test
                    threading.Thread(target=restart, args=(self.mode,), daemon=True).start()  # FIX B5
                    return "success"
                except Exception as ex:
                    logging.error(ex)
                    return "config error", 500
            elif path == "merge-save-config":
                try:
                    self.config = merge_config(request.get_json(), self.config)
                    pwnagotchi.config = merge_config(
                        request.get_json(), pwnagotchi.config
                    )
                    logging.debug("PWNAGOTCHI CONFIG:\n%s" % repr(pwnagotchi.config))
                    if self._agent:
                        self._agent._config = merge_config(
                            request.get_json(), self._agent._config
                        )
                        logging.debug(
                            "    Agent CONFIG:\n%s" % repr(self._agent._config)
                        )
                    logging.debug("   Updated CONFIG:\n%s" % request.get_json())
                    save_config(
                        request.get_json(), "/etc/pwnagotchi/config.toml"
                    )  # test
                    return "success"
                except Exception as ex:
                    logging.error("[webcfg mergesave] %s" % ex)
                    return "config error", 500
        abort(404)
