import glob
import json
import logging
import os
import time
import zipfile
from io import BytesIO

import pwnagotchi
import pwnagotchi.plugins as plugins
from flask import abort, render_template_string, send_file, send_from_directory, jsonify

NETWORK_DATA_FILE = '/etc/pwnagotchi/handshakes-dl-network.json'

HANDSHAKES_TEMPLATE = """
{% extends "base.html" %}
{% set active_page = "handshakes" %}
{% block title %}{{ title }}{% endblock %}
{% block styles %}
{{ super() }}
<style>
    .tabs { display: flex; gap: 0; margin-bottom: 16px; }
    .tabs a {
        padding: 10px 20px; text-decoration: none; color: #333;
        border: 1px solid #ddd; background: #f5f5f5;
    }
    .tabs a.active { background: #fff; border-bottom: 2px solid #333; font-weight: bold; }
    #filter {
        width: 100%; font-size: 16px; padding: 12px 20px 12px 40px;
        border: 1px solid #ddd; margin-bottom: 12px;
    }
</style>
{% endblock %}
{% block script %}
    var shakeList = document.getElementById('list');
    var filter = document.getElementById('filter');
    filter.onkeyup = function() {
        var filterVal = filter.value.toUpperCase();
        var li = shakeList.getElementsByTagName("li");
        for (var i = 0; i < li.length; i++) {
            var txt = li[i].textContent || li[i].innerText;
            li[i].style.display = txt.toUpperCase().indexOf(filterVal) > -1 ? "list-item" : "none";
        }
    }
{% endblock %}
{% block content %}
    <div class="tabs">
        <a href="/plugins/handshakes-dl/" class="active">Handshakes</a>
        <a href="/plugins/handshakes-dl/network">Network Map</a>
    </div>
    <a class="ui-btn" href="/plugins/handshakes-dl/all">Download Zip</a>
    <input type="text" id="filter" placeholder="Search for ..." title="Type in a filter">
    <ul id="list" data-role="listview" style="list-style-type:disc;">
        {% for handshake in handshakes %}
            <li class="file">
                <a href="/plugins/handshakes-dl/{{handshake}}">{{handshake}}</a>
            </li>
        {% endfor %}
    </ul>
{% endblock %}
"""

NETWORK_TEMPLATE = """
{% extends "base.html" %}
{% set active_page = "handshakes" %}
{% block title %}Network Map | {{ title }}{% endblock %}
{% block styles %}
{{ super() }}
<style>
    .tabs { display: flex; gap: 0; margin-bottom: 16px; }
    .tabs a {
        padding: 10px 20px; text-decoration: none; color: #333;
        border: 1px solid #ddd; background: #f5f5f5;
    }
    .tabs a.active { background: #fff; border-bottom: 2px solid #333; font-weight: bold; }
    .view-toggle { margin-bottom: 12px; }
    .view-toggle button {
        padding: 8px 16px; border: 1px solid #999; background: #eee; cursor: pointer;
    }
    .view-toggle button.active { background: #333; color: #fff; }
    #graph-container {
        width: 100%; height: 500px; border: 1px solid #ddd; background: #fafafa;
        position: relative; overflow: hidden;
    }
    #graph-container svg { width: 100%; height: 100%; }
    .node-ap { cursor: pointer; }
    .node-client { cursor: pointer; }
    .link { stroke: #999; stroke-opacity: 0.6; }
    .tooltip {
        position: absolute; padding: 8px 12px; background: rgba(0,0,0,0.85); color: #fff;
        border-radius: 4px; font-size: 12px; pointer-events: none; z-index: 10;
        max-width: 300px; line-height: 1.4;
    }
    #table-container { display: none; }
    table.network { width: 100%; border-collapse: collapse; font-size: 13px; }
    table.network th {
        background: #333; color: #fff; padding: 8px; text-align: left; cursor: pointer;
        user-select: none;
    }
    table.network th:hover { background: #555; }
    table.network td { padding: 6px 8px; border-bottom: 1px solid #ddd; }
    table.network tr.ap-row { background: #f0f0f0; font-weight: bold; cursor: pointer; }
    table.network tr.ap-row:hover { background: #e0e0e0; }
    table.network tr.client-row { background: #fff; }
    table.network tr.client-row td:first-child { padding-left: 24px; }
    table.network tr.client-row.hidden { display: none; }
    .stats-bar {
        display: flex; gap: 20px; margin-bottom: 16px; flex-wrap: wrap;
    }
    .stat-box {
        background: #f5f5f5; border: 1px solid #ddd; padding: 10px 16px;
        border-radius: 4px; text-align: center;
    }
    .stat-box .num { font-size: 24px; font-weight: bold; }
    .stat-box .label { font-size: 11px; color: #666; }
    .legend { display: flex; gap: 12px; margin-bottom: 8px; font-size: 12px; flex-wrap: wrap; }
    .legend span { display: flex; align-items: center; gap: 4px; }
    .legend .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
</style>
{% endblock %}
{% block scripts %}
{{ super() }}
<script src="/js/d3.v7.min.js"></script>
<script>
var networkData = null;

function formatBytes(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
    return (b/1048576).toFixed(1) + ' MB';
}

function formatTime(t) {
    if (!t) return '-';
    var d = new Date(t);
    if (isNaN(d.getTime())) return t.substring(0, 19).replace('T', ' ');
    return d.toLocaleString();
}

var encColors = {
    'WPA2': '#4CAF50', 'WPA3': '#2196F3', 'WPA': '#FF9800',
    'WEP': '#f44336', 'OPEN': '#9E9E9E', '': '#9E9E9E'
};
function encColor(enc) {
    for (var k in encColors) { if (enc && enc.indexOf(k) >= 0) return encColors[k]; }
    return '#9E9E9E';
}

function loadData() {
    fetch('/plugins/handshakes-dl/network/data')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            networkData = data;
            updateStats(data);
            try { renderGraph(data); } catch(e) { console.error('Graph render failed:', e); }
            try { renderTable(data); } catch(e) { console.error('Table render failed:', e); }
        }).catch(function(e) { console.error('Failed to load network data:', e); });
}

function updateStats(data) {
    var aps = Object.keys(data).length;
    var clients = 0, totalData = 0;
    var uniqueClients = {};
    for (var ap in data) {
        var cls = data[ap].clients || {};
        for (var c in cls) {
            uniqueClients[c] = 1;
            totalData += (cls[c].sent || 0) + (cls[c].received || 0);
        }
    }
    clients = Object.keys(uniqueClients).length;
    document.getElementById('stat-aps').textContent = aps;
    document.getElementById('stat-clients').textContent = clients;
    document.getElementById('stat-data').textContent = formatBytes(totalData);
}

function renderGraph(data) {
    var container = document.getElementById('graph-container');
    container.innerHTML = '';
    var w = container.clientWidth || container.offsetWidth || 800;
    var h = container.clientHeight || container.offsetHeight || 500;

    var svg = d3.select(container).append('svg')
        .attr('width', w).attr('height', h);

    var g = svg.append('g');

    // zoom and pan
    var zoom = d3.zoom().scaleExtent([0.2, 5]).on('zoom', function(ev) {
        g.attr('transform', ev.transform);
    });
    svg.call(zoom);

    var tooltip = d3.select(container).append('div').attr('class', 'tooltip').style('display', 'none');

    var nodes = [], links = [], nodeMap = {};
    for (var apMac in data) {
        var ap = data[apMac];
        var apId = 'ap_' + apMac;
        nodes.push({id: apId, mac: apMac, label: ap.hostname || apMac, type: 'ap',
                     enc: ap.encryption || '', vendor: ap.vendor || '', channel: ap.channel || 0,
                     clientCount: Object.keys(ap.clients || {}).length});
        nodeMap[apId] = true;
        var cls = ap.clients || {};
        for (var clMac in cls) {
            var cl = cls[clMac];
            var clId = 'cl_' + clMac;
            if (!nodeMap[clId]) {
                nodes.push({id: clId, mac: clMac, label: cl.vendor || clMac.substring(0,8), type: 'client',
                             vendor: cl.vendor || '', rssi: cl.rssi || 0});
                nodeMap[clId] = true;
            }
            links.push({source: apId, target: clId});
        }
    }

    // scale forces based on node count
    var n = nodes.length;
    var charge = Math.max(-60, -200 / Math.sqrt(n || 1));
    var linkDist = Math.max(30, 80 - n * 0.5);

    var sim = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(links).id(function(d){return d.id}).distance(linkDist))
        .force('charge', d3.forceManyBody().strength(charge))
        .force('center', d3.forceCenter(w/2, h/2))
        .force('collision', d3.forceCollide().radius(function(d){return d.type==='ap'?18:8}))
        .force('x', d3.forceX(w/2).strength(0.05))
        .force('y', d3.forceY(h/2).strength(0.05))
        .alphaDecay(0.02);

    var link = g.append('g').selectAll('line').data(links).enter().append('line')
        .attr('class', 'link').attr('stroke-width', 1);

    var node = g.append('g').selectAll('g').data(nodes).enter().append('g')
        .call(d3.drag().on('start', dragStart).on('drag', dragging).on('end', dragEnd));

    node.filter(function(d){return d.type==='ap'}).append('circle')
        .attr('r', function(d){return 6 + Math.min(d.clientCount * 2, 10)})
        .attr('fill', function(d){return encColor(d.enc)})
        .attr('stroke', '#333').attr('stroke-width', 1.5).attr('class', 'node-ap');

    node.filter(function(d){return d.type==='client'}).append('circle')
        .attr('r', 4).attr('fill', '#78909C').attr('stroke', '#455A64')
        .attr('stroke-width', 1).attr('class', 'node-client');

    node.filter(function(d){return d.type==='ap'}).append('text')
        .text(function(d){return d.label.length > 14 ? d.label.substring(0,14)+'...' : d.label})
        .attr('dy', -10).attr('text-anchor', 'middle')
        .style('font-size', '9px').style('font-weight', 'bold').style('fill', '#333');

    node.on('mouseover', function(ev, d) {
        var html;
        if (d.type === 'ap') {
            html = '<b>' + d.label + '</b><br>MAC: ' + d.mac + '<br>Vendor: ' + (d.vendor||'-') +
                   '<br>Encryption: ' + (d.enc||'-') + '<br>Channel: ' + (d.channel||'-') +
                   '<br>Clients: ' + d.clientCount;
        } else {
            html = '<b>' + d.mac + '</b><br>Vendor: ' + (d.vendor||'Unknown');
            if (d.rssi) html += '<br>Signal: ' + d.rssi + ' dBm';
        }
        tooltip.html(html).style('display', 'block')
            .style('left', (ev.pageX - container.getBoundingClientRect().left + 12) + 'px')
            .style('top', (ev.pageY - container.getBoundingClientRect().top - 12) + 'px');
    }).on('mouseout', function() { tooltip.style('display', 'none'); })
    .on('click', function(ev, d) {
        ev.stopPropagation();
        if (d.type !== 'ap') return;
        node.selectAll('circle').attr('opacity', 0.15);
        link.attr('opacity', 0.05);
        var connected = {};
        connected[d.id] = true;
        links.forEach(function(l) {
            var sid = typeof l.source === 'object' ? l.source.id : l.source;
            var tid = typeof l.target === 'object' ? l.target.id : l.target;
            if (sid === d.id) connected[tid] = true;
            if (tid === d.id) connected[sid] = true;
        });
        node.selectAll('circle').attr('opacity', function(n){return connected[n.id]?1:0.15});
        link.attr('opacity', function(l){
            var sid = typeof l.source === 'object' ? l.source.id : l.source;
            var tid = typeof l.target === 'object' ? l.target.id : l.target;
            return connected[sid] && connected[tid] ? 1 : 0.05;
        });
    });

    svg.on('click', function(ev) {
        if (ev.target === svg.node()) {
            node.selectAll('circle').attr('opacity', 1);
            link.attr('opacity', 0.6);
        }
    });

    sim.on('tick', function() {
        link.attr('x1',function(d){return d.source.x}).attr('y1',function(d){return d.source.y})
            .attr('x2',function(d){return d.target.x}).attr('y2',function(d){return d.target.y});
        node.attr('transform', function(d){return 'translate('+d.x+','+d.y+')'});
    });

    // fit to view after simulation settles
    sim.on('end', function() {
        var bounds = g.node().getBBox();
        if (bounds.width > 0 && bounds.height > 0) {
            var pad = 40;
            var scale = Math.min((w - pad*2) / bounds.width, (h - pad*2) / bounds.height, 1.5);
            var tx = w/2 - (bounds.x + bounds.width/2) * scale;
            var ty = h/2 - (bounds.y + bounds.height/2) * scale;
            svg.transition().duration(500).call(zoom.transform,
                d3.zoomIdentity.translate(tx, ty).scale(scale));
        }
    });

    function dragStart(ev, d) { if (!ev.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }
    function dragging(ev, d) { d.fx = ev.x; d.fy = ev.y; }
    function dragEnd(ev, d) { if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }
}

var tableSortCol = 0, tableSortAsc = true;

function getApSortVal(ap, col) {
    switch(col) {
        case 0: return (ap.data.hostname || ap.mac).toLowerCase();
        case 1: return ap.mac;
        case 2: return (ap.data.vendor || '').toLowerCase();
        case 3: return (ap.data.encryption || '');
        case 4: return ap.data.channel || 0;
        case 5: return ap.data.first_seen || '';
        case 6: return ap.data.last_seen || '';
        case 7: return Object.keys(ap.data.clients || {}).length;
        case 8: return ap.data.pcap_name ? 1 : 0;
        default: return '';
    }
}

function sortTable(col) {
    if (tableSortCol === col) { tableSortAsc = !tableSortAsc; }
    else { tableSortCol = col; tableSortAsc = true; }
    renderTable(networkData);
    // update header arrows
    document.querySelectorAll('table.network th').forEach(function(th, i) {
        th.textContent = th.textContent.replace(/ [▲▼]$/, '');
        if (i === col) th.textContent += tableSortAsc ? ' ▲' : ' ▼';
    });
}

function renderTable(data) {
    var tbody = document.getElementById('network-tbody');
    tbody.innerHTML = '';
    var aps = [];
    for (var mac in data) aps.push({mac: mac, data: data[mac]});

    aps.sort(function(a, b) {
        var va = getApSortVal(a, tableSortCol), vb = getApSortVal(b, tableSortCol);
        var cmp = 0;
        if (typeof va === 'number' && typeof vb === 'number') { cmp = va - vb; }
        else { cmp = String(va).localeCompare(String(vb)); }
        return tableSortAsc ? cmp : -cmp;
    });

    aps.forEach(function(ap, i) {
        var cls = ap.data.clients || {};
        var clCount = Object.keys(cls).length;
        var tr = document.createElement('tr');
        tr.className = 'ap-row';
        tr.dataset.apIdx = i;
        var enc = ap.data.encryption || (ap.data.pcap ? '-' : 'Open');
        var ch = ap.data.channel || '-';
        var firstSeen = ap.data.first_seen ? formatTime(ap.data.first_seen) : '-';
        var lastSeen = ap.data.last_seen ? formatTime(ap.data.last_seen) : '-';
        var hsCell = ap.data.pcap_name
            ? '<a href="/plugins/handshakes-dl/' + ap.data.pcap_name + '" title="Download handshake" style="text-decoration:none;font-size:16px">&#11015; .pcap</a>'
            : '-';
        tr.innerHTML = '<td>' + (ap.data.hostname || ap.mac) + '</td><td>' + ap.mac +
            '</td><td>' + (ap.data.vendor||'-') + '</td><td>' + enc +
            '</td><td>' + ch + '</td><td>' + firstSeen +
            '</td><td>' + lastSeen + '</td><td>' + clCount + ' clients</td><td>' + hsCell + '</td>';
        tr.onclick = function() {
            var rows = tbody.querySelectorAll('.client-row[data-ap="'+i+'"]');
            rows.forEach(function(r) { r.classList.toggle('hidden'); });
        };
        tbody.appendChild(tr);

        for (var clMac in cls) {
            var cl = cls[clMac];
            var ctr = document.createElement('tr');
            ctr.className = 'client-row hidden';
            ctr.dataset.ap = i;
            ctr.innerHTML = '<td></td><td>' + clMac + '</td><td>' + (cl.vendor||'Unknown') +
                '</td><td>' + (cl.rssi ? cl.rssi + ' dBm' : '-') +
                '</td><td>-</td><td>' + formatTime(cl.first_seen) +
                '</td><td>' + formatTime(cl.last_seen) +
                '</td><td>' + formatBytes((cl.sent||0)+(cl.received||0)) + '</td><td></td>';
            tbody.appendChild(ctr);
        }
    });
}

function showView(view) {
    document.getElementById('graph-container').style.display = view === 'graph' ? 'block' : 'none';
    document.getElementById('table-container').style.display = view === 'table' ? 'block' : 'none';
    document.querySelectorAll('.view-toggle button').forEach(function(b) {
        b.classList.toggle('active', b.dataset.view === view);
    });
}

// delay to ensure jQuery Mobile has finished page layout
setTimeout(loadData, 500);
</script>
{% endblock %}
{% block content %}
    <div class="tabs">
        <a href="/plugins/handshakes-dl/">Handshakes</a>
        <a href="/plugins/handshakes-dl/network" class="active">Network Map</a>
    </div>
    <div class="stats-bar">
        <div class="stat-box"><div class="num" id="stat-aps">-</div><div class="label">Access Points</div></div>
        <div class="stat-box"><div class="num" id="stat-clients">-</div><div class="label">Unique Clients</div></div>
        <div class="stat-box"><div class="num" id="stat-data">-</div><div class="label">Total Data</div></div>
    </div>
    <div class="legend">
        <span><span class="dot" style="background:#4CAF50"></span> WPA2</span>
        <span><span class="dot" style="background:#2196F3"></span> WPA3</span>
        <span><span class="dot" style="background:#FF9800"></span> WPA</span>
        <span><span class="dot" style="background:#f44336"></span> WEP</span>
        <span><span class="dot" style="background:#9E9E9E"></span> Unknown</span>
        <span><span class="dot" style="background:#78909C"></span> Client</span>
    </div>
    <div class="view-toggle">
        <button class="active" data-view="graph" onclick="showView('graph')">Graph</button>
        <button data-view="table" onclick="showView('table')">Table</button>
    </div>
    <div id="graph-container"></div>
    <div id="table-container">
        <table class="network">
            <thead>
                <tr><th onclick="sortTable(0)">Name ▲</th><th onclick="sortTable(1)">MAC</th><th onclick="sortTable(2)">Vendor</th>
                    <th onclick="sortTable(3)">Encryption</th><th onclick="sortTable(4)">Channel</th><th onclick="sortTable(5)">First Seen</th><th onclick="sortTable(6)">Last Seen</th><th onclick="sortTable(7)">Clients / Data</th><th onclick="sortTable(8)">Handshake</th></tr>
            </thead>
            <tbody id="network-tbody"></tbody>
        </table>
    </div>
{% endblock %}
"""


class HandshakesDL(plugins.Plugin):
    __author__ = "me@sayakb.com"
    __version__ = "1.0.0"
    __license__ = "GPL3"
    __description__ = "Download handshake captures and view network map from web-ui."

    def __init__(self):
        self.ready = False
        self._network_data = {}
        self._dirty = False
        self._agent = None

    def on_loaded(self):
        logging.info("[HandshakesDL] plugin loaded")
        self._load_network_data()

    def on_config_changed(self, config):
        self.config = config
        self.ready = True

    def on_ready(self, agent):
        self._agent = agent

    def _load_network_data(self):
        try:
            if os.path.isfile(NETWORK_DATA_FILE):
                with open(NETWORK_DATA_FILE, 'r') as f:
                    self._network_data = json.load(f)
                logging.info("[HandshakesDL] loaded network data: %d APs", len(self._network_data))
        except Exception as e:
            logging.error("[HandshakesDL] failed to load network data: %s", e)
            self._network_data = {}

    def _save_network_data(self):
        try:
            with open(NETWORK_DATA_FILE, 'w') as f:
                json.dump(self._network_data, f)
            self._dirty = False
        except Exception as e:
            logging.error("[HandshakesDL] failed to save network data: %s", e)

    def _update_ap(self, ap_mac, hostname='', vendor='', encryption='', channel=0, first_seen=''):
        ap_mac = ap_mac.lower()
        now = first_seen or time.strftime('%Y-%m-%dT%H:%M:%S')
        if ap_mac not in self._network_data:
            self._network_data[ap_mac] = {
                'hostname': hostname, 'vendor': vendor, 'encryption': encryption,
                'channel': channel, 'clients': {}, 'first_seen': now, 'last_seen': now
            }
            self._dirty = True
        else:
            entry = self._network_data[ap_mac]
            if hostname and hostname != '<hidden>':
                entry['hostname'] = hostname
            if vendor:
                entry['vendor'] = vendor
            if encryption:
                entry['encryption'] = encryption
            if channel:
                entry['channel'] = channel
            if 'first_seen' not in entry:
                entry['first_seen'] = now
            entry['last_seen'] = now
            self._dirty = True

    def _update_client(self, ap_mac, cl_mac, vendor='', rssi=0, sent=0, received=0,
                       first_seen='', last_seen=''):
        ap_mac = ap_mac.lower()
        cl_mac = cl_mac.lower()
        if ap_mac not in self._network_data:
            self._network_data[ap_mac] = {
                'hostname': '', 'vendor': '', 'encryption': '', 'channel': 0, 'clients': {}
            }
        clients = self._network_data[ap_mac]['clients']
        if cl_mac not in clients:
            clients[cl_mac] = {
                'vendor': vendor, 'rssi': rssi, 'sent': sent, 'received': received,
                'first_seen': first_seen or time.strftime('%Y-%m-%dT%H:%M:%S'),
                'last_seen': last_seen or time.strftime('%Y-%m-%dT%H:%M:%S')
            }
            self._dirty = True
        else:
            cl = clients[cl_mac]
            if vendor:
                cl['vendor'] = vendor
            if rssi:
                cl['rssi'] = rssi
            if sent > cl.get('sent', 0):
                cl['sent'] = sent
            if received > cl.get('received', 0):
                cl['received'] = received
            cl['last_seen'] = last_seen or time.strftime('%Y-%m-%dT%H:%M:%S')
            self._dirty = True

    def on_bcap_wifi_client_new(self, agent, event):
        try:
            ap = event.get('data', {}).get('AP', {})
            cl = event.get('data', {}).get('Client', {})
            if not ap.get('mac') or not cl.get('mac'):
                return
            self._update_ap(ap['mac'], ap.get('hostname', ''), ap.get('vendor', ''),
                           ap.get('encryption', ''), ap.get('channel', 0))
            self._update_client(ap['mac'], cl['mac'], cl.get('vendor', ''),
                               cl.get('rssi', 0), cl.get('sent', 0), cl.get('received', 0),
                               cl.get('first_seen', ''), cl.get('last_seen', ''))
        except Exception as e:
            logging.debug("[HandshakesDL] client_new event error: %s", e)

    def on_bcap_wifi_ap_new(self, agent, event):
        try:
            ap = event.get('data', {})
            if not ap.get('mac'):
                return
            self._update_ap(ap['mac'], ap.get('hostname', ''), ap.get('vendor', ''),
                           ap.get('encryption', ''), ap.get('channel', 0))
        except Exception as e:
            logging.debug("[HandshakesDL] ap_new event error: %s", e)

    def _import_pcap_aps(self):
        """Import AP MACs and SSIDs from existing pcap filenames."""
        try:
            hs_dir = self.config.get('bettercap', {}).get('handshakes', '/home/pi/handshakes')
            for fname in os.listdir(hs_dir):
                if not fname.endswith('.pcap') or fname.endswith('.pcap.failed'):
                    continue
                fpath = os.path.join(hs_dir, fname)
                if os.path.getsize(fpath) == 0:
                    continue
                base = fname[:-5]  # remove .pcap
                parts = base.rsplit('_', 1)
                if len(parts) != 2 or len(parts[1]) != 12:
                    continue
                ssid = parts[0]
                raw_mac = parts[1].lower()
                ap_mac = ':'.join(raw_mac[i:i+2] for i in range(0, 12, 2))
                if ap_mac not in self._network_data:
                    mtime = os.path.getmtime(fpath)
                    ts = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(mtime))
                    self._network_data[ap_mac] = {
                        'hostname': ssid, 'vendor': '', 'encryption': '',
                        'channel': 0, 'clients': {}, 'pcap': True,
                        'pcap_name': base, 'first_seen': ts
                    }
                    self._dirty = True
                else:
                    entry = self._network_data[ap_mac]
                    if not entry.get('hostname') or entry['hostname'] == '<hidden>':
                        entry['hostname'] = ssid
                    entry['pcap'] = True
                    entry['pcap_name'] = base
                    self._dirty = True
        except Exception as e:
            logging.debug("[HandshakesDL] pcap import error: %s", e)

    def _snapshot_session(self):
        """Query bettercap API directly and update network data from live session."""
        self._import_pcap_aps()
        try:
            from pwnagotchi.bettercap import Client
            bc = Client('127.0.0.1', 'http', 8081, 'pwnagotchi', 'pwnagotchi')
            s = bc.session()
            for ap in s.get('wifi', {}).get('aps', []):
                if not ap.get('mac'):
                    continue
                self._update_ap(ap['mac'], ap.get('hostname', ''), ap.get('vendor', ''),
                               ap.get('encryption', ''), ap.get('channel', 0))
                for cl in ap.get('clients', []):
                    if not cl.get('mac'):
                        continue
                    self._update_client(ap['mac'], cl['mac'], cl.get('vendor', ''),
                                       cl.get('rssi', 0), cl.get('sent', 0), cl.get('received', 0),
                                       cl.get('first_seen', ''), cl.get('last_seen', ''))
            if self._dirty:
                self._save_network_data()
        except Exception as e:
            logging.debug("[HandshakesDL] session snapshot error: %s", e)

    def on_epoch(self, agent, epoch, epoch_data):
        self._snapshot_session()

    def on_webhook(self, path, request):
        if not self.ready:
            return "Plugin not ready"

        if path == "/" or not path:
            handshakes = glob.glob(
                os.path.join(self.config["bettercap"]["handshakes"], "*.pcap"))
            handshakes = [os.path.basename(p)[:-5] for p in handshakes]
            return render_template_string(
                HANDSHAKES_TEMPLATE,
                title="Handshakes | " + pwnagotchi.name(),
                handshakes=handshakes,
            )
        elif path == "network":
            return render_template_string(
                NETWORK_TEMPLATE,
                title=pwnagotchi.name(),
            )
        elif path == "network/data":
            self._snapshot_session()
            return jsonify(self._network_data)
        elif path == "all":
            logging.info("[HandshakesDL] creating Zip-File in memory")
            memory_file = BytesIO()
            with zipfile.ZipFile(memory_file, "w") as zf:
                files = glob.glob(
                    os.path.join(self.config["bettercap"]["handshakes"], "*.pcap"))
                try:
                    for individualFile in files:
                        zf.write(individualFile)
                except Exception as e:
                    logging.error("[HandshakesDL] %s", e)
                    abort(404)
            memory_file.seek(0)
            return send_file(memory_file,
                             attachment_filename="handshakes.zip",
                             as_attachment=True)
        else:
            dir = self.config["bettercap"]["handshakes"]
            try:
                return send_from_directory(directory=dir,
                                           path=path + ".pcap",
                                           as_attachment=True)
            except FileNotFoundError:
                abort(404)
