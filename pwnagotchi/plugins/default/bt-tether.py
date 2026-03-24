"""
Bluetooth Tether Plugin for Pwnagotchi

Required System Packages:
    sudo apt-get update
    sudo apt-get install -y bluez network-manager python3-dbus python3-toml

Features:
- Bluetooth tethering to mobile phones (iOS & Android)
- Auto-discovery of trusted devices with tethering capability
- Works with iOS randomized MAC addresses
- Auto-reconnect functionality
- Web UI for easy device pairing and management
- No manual MAC configuration needed

Setup:
1. Install packages: sudo apt-get install -y bluez network-manager python3-dbus python3-toml
2. Enable services:
   sudo systemctl enable bluetooth && sudo systemctl start bluetooth
   sudo systemctl enable NetworkManager && sudo systemctl start NetworkManager
3. Access web UI at http://<pwnagotchi-ip>:8080/plugins/bt-tether
4. Scan and pair your phone - it will auto-connect from then on!

Configuration (config.toml):

    [main.plugins.bt-tether]
    enabled = true
    auto_reconnect = true                    # Auto reconnect on disconnect (default: true)
    show_on_screen = true                    # Master switch: show status on display
    show_mini_status = true                  # Show mini status indicator (C/N/P/D)
    mini_status_position = [110, 0]          # Position for mini status
    show_detailed_status = true              # Show detailed status line with IP
    detailed_status_position = [0, 82]       # Position for detailed status line
"""

import subprocess
import threading
import time
import logging
import os
import re
import traceback
import json
import datetime
from pwnagotchi.plugins import Plugin
from flask import render_template_string, request, jsonify
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
from pwnagotchi import plugins
import pwnagotchi

try:
    import dbus
    import dbus.service

    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    logging.warning("[bt-tether] dbus/GLib not available, BLE advertising disabled")


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
  <head>
    <title>Bluetooth Tether</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Cpath fill='%2358a6ff' d='M50 10 L70 25 L70 45 L50 60 L50 90 L30 75 L30 55 L50 40 L50 10 M50 40 L50 60'/%3E%3C/svg%3E" />
    <style>
      body { font-family: sans-serif; padding: 20px; max-width: 600px; margin: 0 auto; background: #0d1117; color: #d4d4d4; }
      .card { background: #161b22; padding: 20px; border-radius: 8px; margin-bottom: 16px; box-shadow: 0 2px 4px rgba(0,0,0,0.3); border: 1px solid #30363d; }
      h2 { margin: 0 0 20px 0; color: #58a6ff; }
      h3 { color: #d4d4d4; }
      h4 { color: #8b949e; }
      input { padding: 10px; font-size: 14px; border: 1px solid #30363d; border-radius: 4px; text-transform: uppercase; background: #0d1117; color: #d4d4d4; }
      input:focus { outline: none; border-color: #58a6ff; background: #161b22; }
      button { padding: 10px 20px; background: transparent; color: #3fb950; border: 1px solid #3fb950; cursor: pointer; font-size: 14px; border-radius: 4px; margin-right: 8px; min-height: 42px; display: inline-flex; align-items: center; justify-content: center; }
      button:hover { background: rgba(63, 185, 80, 0.1); border-color: #3fb950; }
      button.danger { color: #f85149; border-color: #f85149; background: transparent; }
      button.danger:hover { background: rgba(248, 81, 73, 0.1); border-color: #f85149; }
      button.success { color: #3fb950; border-color: #3fb950; background: transparent; }
      button.success:hover { background: rgba(63, 185, 80, 0.1); border-color: #3fb950; }
      button:disabled { background: transparent; color: #8b949e; cursor: not-allowed; border-color: #30363d; }
      .status-item { padding: 8px; margin: 4px 0; border-radius: 4px; background: #161b22; border: 1px solid #30363d; color: #d4d4d4; }
      .status-good { background: rgba(46, 160, 67, 0.15); color: #3fb950; border-color: #3fb950; }
      .status-bad { background: rgba(248, 81, 73, 0.15); color: #f85149; border-color: #f85149; }
      .device-item { padding: 12px; margin: 8px 0; border: 1px solid #30363d; border-radius: 4px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; background: #0d1117; color: #d4d4d4; }
      .device-item:hover { background: #161b22; border-color: #58a6ff; }
      .message-box { padding: 12px; border-radius: 4px; margin: 12px 0; border-left: 4px solid; }
      .message-info { background: rgba(88, 166, 255, 0.1); color: #79c0ff; border-color: #79c0ff; }
      .message-success { background: rgba(63, 185, 80, 0.1); color: #3fb950; border-color: #3fb950; }
      .message-warning { background: rgba(214, 159, 0, 0.1); color: #d29922; border-color: #d29922; }
      .message-error { background: rgba(248, 81, 73, 0.1); color: #f85149; border-color: #f85149; }
      .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #30363d; 
                 border-top: 2px solid #58a6ff; border-radius: 50%; animation: spin 1s linear infinite; margin-right: 8px; vertical-align: middle; }
      @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
      .mac-editor { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
      .mac-editor input { flex: 1; min-width: 200px; }
      .mac-editor button { white-space: nowrap; }
      .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
      .header h2 { margin: 0; flex: 1; }
      .header button { margin-left: 12px; }
      button.outline { color: #ffffff; border-color: #ffffff; }
      button.outline:hover { background: rgba(255, 255, 255, 0.1); border-color: #ffffff; }
      @media (max-width: 600px) {
        .mac-editor { flex-direction: column; align-items: stretch; }
        .mac-editor input { width: 100%; }
        .mac-editor button { width: 100%; margin: 0 !important; }
      }
    </style>
  </head>
  <body>
    <div class="header">
      <div>
        <h2>🔷 Bluetooth Tether</h2>
        <div style="font-size: 12px; color: #8b949e; margin-top: 2px;">v{{ version }}</div>
      </div>
      <button class="outline" onclick="window.location.href='/plugins'" style="margin: 0;">Plugins</button>
    </div>
    
    <!-- Phone Connection & Status -->
    <div class="card" id="phoneConnectionCard">
      <h3 style="margin: 0 0 12px 0;">📱 Connection Status</h3>
      <div id="trustedDevicesInfo" style="background: #0d1117; color: #d4d4d4; padding: 12px; border-radius: 4px; margin-bottom: 12px; font-family: 'Courier New', monospace; font-size: 12px; line-height: 1.5;">
        <div style="color: #888; margin-bottom: 4px;">Trusted Devices:</div>
        <div id="trustedDevicesSummary" style="color: #4ec9b0; font-size: 14px;">Loading...</div>
      </div>
      
      <!-- Status in output style -->
      <div style="background: #0d1117; color: #d4d4d4; padding: 12px; border-radius: 4px; margin-bottom: 12px; font-family: 'Courier New', monospace; font-size: 12px; line-height: 1.5;">
        <div style="color: #888; margin-bottom: 8px;">Connection Status:</div>
        <div id="statusActiveConnection" style="display: none; margin: 4px 0; padding: 8px; background: rgba(78, 201, 176, 0.1); border-left: 3px solid #4ec9b0; margin-bottom: 8px;"></div>
        <div id="statusPaired" style="margin: 4px 0;">📱 Paired: <span>Checking...</span></div>
        <div id="statusTrusted" style="margin: 4px 0;">🔐 Trusted: <span>Checking...</span></div>
        <div id="statusConnected" style="margin: 4px 0;">🔵 Connected: <span>Checking...</span></div>
        <div id="statusInternet" style="margin: 4px 0;">🌐 Internet: <span>Checking...</span></div>
        <div id="statusIP" style="display: none; margin: 4px 0;">🔢 IP Address: <span></span></div>
      </div>
      
      <!-- Hidden input for JavaScript to access MAC value -->
      <input type="hidden" id="macInput" value="{{ mac }}" />
      
      <!-- Output Section (shown above connect button) -->
      <div style="margin-bottom: 12px;">
        <h4 style="margin: 0 0 8px 0; color: #8b949e; font-size: 14px;">📋 Output</h4>
        <div id="logViewer">
          <div style="background: #0d1117; color: #d4d4d4; padding: 12px; padding-right: 16px; border-radius: 4px; font-family: 'Courier New', monospace; font-size: 12px; max-height: 300px; overflow-y: auto; line-height: 1.5;" id="logContent">
            <div style="color: #888;">Fetching logs...</div>
          </div>
        </div>
        <style>
          #logContent::-webkit-scrollbar {
            width: 5px;
          }
          #logContent::-webkit-scrollbar-track {
            background: #0d1117;
            border-radius: 4px;
          }
          #logContent::-webkit-scrollbar-thumb {
            background: #30363d;
            border-radius: 4px;
          }
          #logContent::-webkit-scrollbar-thumb:hover {
            background: #484f58;
          }
        </style>
      </div>
      
      <!-- Connect/Disconnect Actions -->
      <div id="connectActions">
        <button class="success" onclick="quickConnect()" id="quickConnectBtn" style="width: 100%; margin: 0 0 8px 0;">
          ⚡ Connect to Phone
        </button>
      </div>
      
      <!-- Disconnect Section -->
      <div id="disconnectSection" style="display: none;">
        <button class="danger" onclick="disconnectDevice()" id="disconnectBtn" style="width: 100%; margin: 0 0 8px 0;">
          🔌 Disconnect
        </button>
      </div>
      
      <!-- Device Discovery Section -->
      <div id="deviceDiscoverySection" style="display: none; margin-top: 16px; padding-top: 16px; border-top: 1px solid #30363d;">
        <h4 style="margin: 0 0 12px 0;">🔍 Discover Devices</h4>
        <p style="color: #8b949e; font-size: 13px; margin: 0 0 12px 0;">Scan for nearby Bluetooth devices to pair:</p>
        <button class="success" onclick="scanDevices()" id="scanBtn" style="width: 100%; margin: 0 0 12px 0;">
          🔍 Scan
        </button>
        
        <!-- Discovered Devices List -->
        <div id="scanResults" style="display: none;">
          <h5 style="margin: 0 0 8px 0; color: #8b949e;">Discovered Devices:</h5>
          <div id="scanStatus" style="color: #8b949e; margin: 8px 0; font-size: 13px;">Scanning...</div>
          <div id="deviceList"></div>
        </div>
      </div>
    </div>
    
    <!-- Test Internet Connectivity -->
    <div class="card" id="testInternetCard" style="display: none;">
      <h3 style="margin: 0 0 12px 0;">🔍 Test Internet Connectivity</h3>
      <button onclick="testInternet()" id="testInternetBtn" style="width: 100%; margin: 0 0 12px 0;">
        🔍 Test Internet Connectivity
      </button>
      
      <!-- Test Results -->
      <div id="testResults" style="display: none;">
        <div id="testResultsMessage" class="message-box message-info"></div>
      </div>
    </div>
    
    <script>
      const macInput = document.getElementById("macInput");
      let statusInterval = null;
      let logInterval = null;

      // Load trusted devices on page load
      loadTrustedDevicesSummary();
      
      // Show initializing state first
      setInitializingStatus();
      // Then check actual connection status
      setTimeout(checkConnectionStatus, 1000);
      
      // Start log polling immediately
      refreshLogs();
      startLogPolling();

      function setInitializingStatus() {
        document.getElementById("statusPaired").innerHTML = 
          `📱 Paired: <span style="color: #8b949e;">🔄 Initializing...</span>`;
        
        document.getElementById("statusTrusted").innerHTML = 
          `🔐 Trusted: <span style="color: #8b949e;">🔄 Initializing...</span>`;
        
        document.getElementById("statusConnected").innerHTML = 
          `🔵 Connected: <span style="color: #8b949e;">🔄 Initializing...</span>`;
        
        document.getElementById("statusInternet").innerHTML = 
          `🌐 Internet: <span style="color: #8b949e;">🔄 Initializing...</span>`;
        
        document.getElementById('statusIP').style.display = 'none';
        document.getElementById('statusActiveConnection').style.display = 'none';
        
        const connectBtn = document.getElementById('quickConnectBtn');
        connectBtn.disabled = true;
        connectBtn.innerHTML = '<span class="spinner"></span> Initializing...';
      }

      async function checkConnectionStatus() {
        const mac = macInput.value.trim();
        if (!/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(mac)) {
          // No valid MAC in input - try to get from backend status
          try {
            const statusResponse = await fetch(`/plugins/bt-tether/status`);
            const statusData = await statusResponse.json();
            
            // If backend has a current MAC, use it
            if (statusData.mac && /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(statusData.mac)) {
              // We have a MAC from backend, check its status
              const response = await fetch(`/plugins/bt-tether/connection-status?mac=${encodeURIComponent(statusData.mac)}`);
              const data = await response.json();
              
              // Update UI with backend MAC
              macInput.value = statusData.mac;
              updateStatusDisplay(statusData, data);
              return;
            }
          } catch (err) {
            console.error('Failed to get backend status:', err);
          }
          
          // No valid MAC - hide connect button and show disconnected state
          const connectBtn = document.getElementById('quickConnectBtn');
          const disconnectSection = document.getElementById('disconnectSection');
          connectBtn.style.display = 'none';
          disconnectSection.style.display = 'none';
          
          // Update status to show disconnected/no device state
          document.getElementById("statusPaired").innerHTML = 
            `📱 Paired: <span style="color: #f48771;">✗ No</span>`;
          
          document.getElementById("statusTrusted").innerHTML = 
            `🔐 Trusted: <span style="color: #f48771;">✗ No</span>`;
          
          document.getElementById("statusConnected").innerHTML = 
            `🔵 Connected: <span style="color: #f48771;">✗ No</span>`;
          
          document.getElementById("statusInternet").innerHTML = 
            `🌐 Internet: <span style="color: #f48771;">✗ Not Active</span>`;
          
          document.getElementById('statusIP').style.display = 'none';
          document.getElementById('statusActiveConnection').style.display = 'none';
          
          return;
        }
        
        try {
          // First check the plugin's internal status
          const statusResponse = await fetch(`/plugins/bt-tether/status`);
          const statusData = await statusResponse.json();
          
          const response = await fetch(`/plugins/bt-tether/connection-status?mac=${encodeURIComponent(mac)}`);
          const data = await response.json();
          
          updateStatusDisplay(statusData, data);
          
        } catch (error) {
          console.error('Status check failed:', error);
        }
      }
      
      function updateStatusDisplay(statusData, data) {
        // Determine screen status letter (C/N/P/D)
        let screenStatus = 'D';
        if (data.pan_active) {
          screenStatus = 'C';  // Connected with internet
        } else if (data.connected) {
          screenStatus = 'N';  // Connected but no internet
        } else if (data.paired) {
          screenStatus = 'P';  // Paired but not connected
        }
        
        document.getElementById("statusPaired").innerHTML = 
          `📱 Paired: <span style="color: ${data.paired ? '#4ec9b0' : '#f48771'};">${data.paired ? '✓ Yes' : '✗ No'}</span>`;
        
        document.getElementById("statusTrusted").innerHTML = 
          `🔐 Trusted: <span style="color: ${data.trusted ? '#4ec9b0' : '#f48771'};">${data.trusted ? '✓ Yes' : '✗ No'}</span>`;
        
        document.getElementById("statusConnected").innerHTML = 
          `🔵 Connected: <span style="color: ${data.connected ? '#4ec9b0' : '#f48771'};">${data.connected ? '✓ Yes' : '✗ No'}</span>`;
        
        document.getElementById("statusInternet").innerHTML = 
          `🌐 Internet: <span style="color: ${data.pan_active ? '#4ec9b0' : '#f48771'};">${data.pan_active ? '✓ Active' : '✗ Not Active'}</span>${data.interface ? ` <span style="color: #888;">(${data.interface})</span>` : ''}`;
        
        // Show/hide test internet card based on connection status
        const testInternetCard = document.getElementById('testInternetCard');
        if (data.pan_active) {
          testInternetCard.style.display = 'block';
        } else {
          testInternetCard.style.display = 'none';
        }
        
        // Show IP address if available
        const statusIPElement = document.getElementById('statusIP');
        if (data.ip_address && data.pan_active) {
          statusIPElement.style.display = 'block';
          statusIPElement.innerHTML = `🔢 IP Address: <span style="color: #4ec9b0;">${data.ip_address}</span>`;
        } else {
          statusIPElement.style.display = 'none';
        }
        
        // Show active connection type inside status card
        const statusActiveConnection = document.getElementById('statusActiveConnection');
        
        if (data.default_route_interface) {
          const isUsingBluetooth = data.default_route_interface === data.interface;
          
          // Determine connection type and details
          let connType = 'Unknown';
          let connEmoji = '🔌';
          let connDetails = '';
          
          if (data.default_route_interface.startsWith('usb')) {
            connType = 'USB Tethering';
            connEmoji = '🔌';
            if (data.pan_active && !isUsingBluetooth) {
              connDetails = '<div style="color: #ce9178; margin-top: 4px; font-size: 11px;">💡 Bluetooth is on standby • USB has priority due to higher speed</div>';
            }
          } else if (data.default_route_interface.startsWith('bnep')) {
            connType = 'Bluetooth Tethering';
            connEmoji = '📱';
          } else if (data.default_route_interface.startsWith('eth')) {
            connType = 'Ethernet';
            connEmoji = '🌐';
            if (data.pan_active) {
              connDetails = '<div style="color: #ce9178; margin-top: 4px; font-size: 11px;">💡 Bluetooth is on standby • Ethernet is active</div>';
            }
          } else if (data.default_route_interface.startsWith('wlan')) {
            connType = 'Wi-Fi';
            connEmoji = '📶';
            if (data.pan_active) {
              connDetails = '<div style="color: #ce9178; margin-top: 4px; font-size: 11px;">💡 Bluetooth is on standby • Wi-Fi is active</div>';
            }
          }
          
          statusActiveConnection.style.display = 'block';
          statusActiveConnection.innerHTML = `${connEmoji} <span style="color: #4ec9b0; font-weight: bold;">${connType}</span> <span style="color: #888;">(${data.default_route_interface})</span>${connDetails}`;
        } else {
          statusActiveConnection.style.display = 'none';
        }
        
        // Manage polling based on connection state
        if (statusData.status === 'PAIRING' || statusData.status === 'TRUSTING' || statusData.status === 'CONNECTING' || statusData.status === 'RECONNECTING' || statusData.connection_in_progress) {
          // Actively connecting - poll faster (every 2 seconds)
          if (!statusInterval || statusInterval._interval !== 2000) {
            console.log('Connection in progress - fast polling (2s)');
            stopStatusPolling();
            statusInterval = setInterval(checkConnectionStatus, 2000);
            statusInterval._interval = 2000;
          }
        } else if (data.connected || data.paired) {
          // Connected or paired - poll slower (every 10 seconds) to keep status updated
          if (!statusInterval || statusInterval._interval !== 10000) {
            console.log('Connected/paired - slow polling (10s)');
            stopStatusPolling();
            statusInterval = setInterval(checkConnectionStatus, 10000);
            statusInterval._interval = 10000;
          }
        } else {
          // Disconnected and not paired - poll very slowly (every 30 seconds) to catch new devices
          if (!statusInterval || statusInterval._interval !== 30000) {
            console.log('Disconnected - slow polling (30s)');
            stopStatusPolling();
            statusInterval = setInterval(checkConnectionStatus, 30000);
            statusInterval._interval = 30000;
          }
        }
        
        // Update button states
        // Show/hide connect/disconnect buttons based on connection status
        const connectBtn = document.getElementById('quickConnectBtn');
        const disconnectSection = document.getElementById('disconnectSection');
        
        // Check if ANY operation is in progress
        const operationInProgress = statusData.disconnecting || statusData.untrusting || statusData.connection_in_progress || statusData.status === 'PAIRING' || statusData.status === 'TRUSTING' || statusData.status === 'CONNECTING' || statusData.status === 'RECONNECTING';
        
        // Set button state based on current status
        if (statusData.disconnecting) {
          // Show disconnecting state - hide all buttons during disconnect
          connectBtn.style.display = 'none';
          disconnectSection.style.display = 'none';
        } else if (statusData.untrusting) {
          // Show untrusting state - hide all buttons during untrust
          connectBtn.style.display = 'none';
          disconnectSection.style.display = 'none';
        } else if (statusData.status === 'PAIRING' || statusData.status === 'TRUSTING' || statusData.status === 'CONNECTING' || statusData.status === 'RECONNECTING') {
          // Show spinner during connection operations - hide disconnect section during connect
          connectBtn.disabled = true;
          connectBtn.innerHTML = '<span class="spinner"></span> Connecting...';
          connectBtn.style.display = 'block';
          disconnectSection.style.display = 'none';  // Hide disconnect while pairing/connecting
        } else {
          // Reset button to normal state when not in any operation
          connectBtn.disabled = false;
          connectBtn.innerHTML = '⚡ Connect to Phone';
          
          // Show/hide buttons based on connection status when no operation in progress
          if (data.connected) {
            connectBtn.style.display = 'none';
            disconnectSection.style.display = 'block';
          } else if (data.paired && data.trusted) {
            connectBtn.style.display = 'block';
            disconnectSection.style.display = 'block';
          } else if (data.paired) {
            connectBtn.style.display = 'none';
            disconnectSection.style.display = 'block';
          } else {
            // Not paired - hide both connect and disconnect buttons
            connectBtn.style.display = 'none';
            disconnectSection.style.display = 'none';
          }
        }
        
        // Only refresh trusted devices summary if connection state changed or scanning state changed
        // This prevents frequent calls that might interfere with scan results display
        if (!window.lastStatusUpdate || 
            (window.lastStatusUpdate.connected !== (statusData.mac && data.connected)) ||
            (window.lastStatusUpdate.scanning !== statusData.scanning)) {
          loadTrustedDevicesSummary();
          window.lastStatusUpdate = {
            connected: statusData.mac && data.connected,
            scanning: statusData.scanning
          };
        }
      }

      function startStatusPolling() {
        if (statusInterval) clearInterval(statusInterval);
        // Poll every 2 seconds during connection - passkey is shown in logs
        statusInterval = setInterval(checkConnectionStatus, 2000);
      }

      function stopStatusPolling() {
        if (statusInterval) {
          clearInterval(statusInterval);
          statusInterval = null;
        }
      }

      async function quickConnect() {
        const mac = macInput.value.trim();
        if (!mac || !/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(mac)) {
          showFeedback("Please enter your phone's MAC address first!", "warning");
          return;
        }

        const quickConnectBtn = document.getElementById('quickConnectBtn');
        quickConnectBtn.disabled = true;
        quickConnectBtn.innerHTML = '<span class="spinner"></span> Connecting...';
        
        showFeedback("Connecting to phone... Watch for pairing dialog!", "info");
        
        try {
          const response = await fetch(`/plugins/bt-tether/connect?mac=${encodeURIComponent(mac)}`, { method: 'GET' });
          const data = await response.json();
          
          if (data.success) {
            showFeedback("Connection started! Check your phone for the pairing dialog.", "success");
            startStatusPolling();
            // Don't reset button - let status polling handle button states
          } else {
            showFeedback("Connection failed: " + data.message, "error");
            // Only reset button on failure
            quickConnectBtn.disabled = false;
            quickConnectBtn.innerHTML = '⚡ Connect to Phone';
          }
        } catch (error) {
          showFeedback("Connection failed: " + error.message, "error");
          // Only reset button on error
          quickConnectBtn.disabled = false;
          quickConnectBtn.innerHTML = '⚡ Connect to Phone';
        }
      }

      async function scanDevices() {
        const scanBtn = document.getElementById('scanBtn');
        const scanResults = document.getElementById('scanResults');
        const scanStatus = document.getElementById('scanStatus');
        const deviceList = document.getElementById('deviceList');

        scanBtn.disabled = true;
        scanBtn.innerHTML = '<span class="spinner"></span> Scanning...';
        scanResults.style.display = 'block';
        deviceList.innerHTML = '';
        scanStatus.innerHTML = '<span class="spinner"></span> Scanning for devices...';

        showFeedback("Scanning for devices... Keep phone Bluetooth settings open!", "info");

        try {
          const response = await fetch('/plugins/bt-tether/scan', { method: 'GET' });
          await response.json();

          // Poll /scan-progress every 2 seconds to show devices as they appear
          let pollCount = 0;
          const maxPolls = 16;
          let lastDeviceCount = 0;
          let scanProgressInterval = setInterval(async () => {
            pollCount++;

            try {
              const progressResponse = await fetch('/plugins/bt-tether/scan-progress');
              const progressData = await progressResponse.json();

              if (progressData.devices && progressData.devices.length > lastDeviceCount) {
                lastDeviceCount = progressData.devices.length;
                deviceList.innerHTML = '';
                progressData.devices.forEach(device => {
                  const div = document.createElement('div');
                  div.className = 'device-item';
                  div.innerHTML = `
                    <div style="flex: 1; font-family: 'Courier New', monospace; font-size: 12px;">
                      <b>${device.name}</b><br>
                      <small style="color: #888;">${device.mac}</small>
                    </div>
                    <button onclick="pairAndConnectDevice('${device.mac}', '${device.name.replace(/'/g, "\\'")}'); return false;" class="success" style="margin: 0; padding: 6px 12px; font-size: 12px;">Pair</button>
                  `;
                  deviceList.appendChild(div);
                });
                scanStatus.innerHTML = `<span class="spinner"></span> Found ${progressData.devices.length} device(s)... still scanning`;
              }

              if (!progressData.scanning) {
                clearInterval(scanProgressInterval);
                if (progressData.devices && progressData.devices.length > 0) {
                  scanStatus.textContent = `Scan complete - Found ${progressData.devices.length} device(s):`;
                  showFeedback(`Found ${progressData.devices.length} device(s). Click Pair to connect!`, "success");
                } else {
                  scanStatus.textContent = 'Scan complete - No devices found';
                  deviceList.innerHTML = '';
                  showFeedback("No devices found. Make sure phone Bluetooth is ON and visible.", "warning");
                }
                scanBtn.disabled = false;
                scanBtn.innerHTML = '🔍 Scan';
              } else if (pollCount >= maxPolls) {
                clearInterval(scanProgressInterval);
                scanStatus.textContent = 'Scan complete';
                scanBtn.disabled = false;
                scanBtn.innerHTML = '🔍 Scan';
              }
            } catch (e) {
              console.log('Scan progress poll error:', e);
            }
          }, 2000);
        } catch (error) {
          scanStatus.textContent = 'Scan failed';
          showFeedback("Scan failed: " + error.message, "error");
          scanBtn.disabled = false;
          scanBtn.innerHTML = '🔍 Scan';
        }
      }

      async function loadTrustedDevicesSummary() {
        try {
          // Check if plugin is initializing first
          const statusResponse = await fetch('/plugins/bt-tether/status');
          const statusData = await statusResponse.json();
          
          const summaryDiv = document.getElementById('trustedDevicesSummary');
          const deviceDiscoverySection = document.getElementById('deviceDiscoverySection');
          
          // Hide device discovery section during initialization, pairing, connecting, reconnecting, disconnecting, or untrusting
          const isConnecting = statusData.initializing || 
                               statusData.disconnecting ||
                               statusData.untrusting ||
                               statusData.connection_in_progress ||
                               statusData.status === 'PAIRING' || 
                               statusData.status === 'CONNECTING' || 
                               statusData.status === 'RECONNECTING';
          
          // Show initializing state if plugin is still starting up
          if (statusData.initializing) {
            summaryDiv.innerHTML = '<span style="color: #8b949e;">🔄 Initializing Bluetooth...</span>';
            deviceDiscoverySection.style.display = 'none';
            // Poll again in 2 seconds to detect when initialization completes
            setTimeout(loadTrustedDevicesSummary, 2000);
            return;
          }
          
          // Show disconnecting/untrusting state
          if (statusData.disconnecting) {
            summaryDiv.innerHTML = '<span class="spinner"></span><span style="color: #f85149;">Disconnecting...</span>';
            deviceDiscoverySection.style.display = 'none';
            setTimeout(loadTrustedDevicesSummary, 1500);
            return;
          }
          
          if (statusData.untrusting) {
            summaryDiv.innerHTML = '<span class="spinner"></span><span style="color: #f85149;">Removing trust...</span>';
            deviceDiscoverySection.style.display = 'none';
            setTimeout(loadTrustedDevicesSummary, 1500);
            return;
          }

          // Show spinner during pairing/connecting operations
          if (statusData.status === 'PAIRING') {
            summaryDiv.innerHTML = '<span class="spinner"></span><span style="color: #d29922;">Pairing...</span>';
            deviceDiscoverySection.style.display = 'none';
            setTimeout(loadTrustedDevicesSummary, 1500);
            return;
          }

          if (statusData.status === 'TRUSTING') {
            summaryDiv.innerHTML = '<span class="spinner"></span><span style="color: #d29922;">Trusting device...</span>';
            deviceDiscoverySection.style.display = 'none';
            setTimeout(loadTrustedDevicesSummary, 1500);
            return;
          }

          if (statusData.status === 'CONNECTING' || statusData.status === 'RECONNECTING') {
            summaryDiv.innerHTML = '<span class="spinner"></span><span style="color: #58a6ff;">Connecting...</span>';
            deviceDiscoverySection.style.display = 'none';
            setTimeout(loadTrustedDevicesSummary, 1500);
            return;
          }
          
          const response = await fetch('/plugins/bt-tether/trusted-devices');
          const data = await response.json();
          
          if (data.devices && data.devices.length > 0) {
            const napDevices = data.devices.filter(d => d.has_nap);
            const connectedDevice = napDevices.find(d => d.connected);
            
            // Hide device discovery section when trusted devices exist OR when connecting
            deviceDiscoverySection.style.display = 'none';
            
            if (connectedDevice) {
              summaryDiv.innerHTML = `<span style="color: #3fb950;">🔵 Connected to ${connectedDevice.name}</span><br><small style="color: #888;">${connectedDevice.mac}</small>`;
            } else if (napDevices.length > 0) {
              summaryDiv.innerHTML = napDevices.map(d => 
                `<div style="margin: 4px 0;">📱 ${d.name}<br><small style="color: #888;">${d.mac}</small></div>`
              ).join('');
            } else {
              summaryDiv.innerHTML = `<span style="color: #f85149;">${data.devices.length} paired device(s) but none support tethering</span>`;
              // Show device discovery section if no devices support tethering AND not connecting
              deviceDiscoverySection.style.display = isConnecting ? 'none' : 'block';
            }
          } else {
            // Only show device discovery section when no devices AND not connecting
            if (isConnecting) {
              deviceDiscoverySection.style.display = 'none';
              summaryDiv.innerHTML = '<span style="color: #8b949e;">Connecting...</span>';
            } else {
              deviceDiscoverySection.style.display = 'block';
              summaryDiv.innerHTML = '<span style="color: #8b949e;">No paired devices - scan to pair a device</span>';
            }
          }
        } catch (error) {
          document.getElementById('trustedDevicesSummary').innerHTML = '<span style="color: #f85149;">Error loading devices</span>';
        }
      }

      async function pairAndConnectDevice(mac, name) {
        showFeedback(`Starting pairing with ${name}... Watch for pairing dialog!`, "info");
        
        // Hide scan results and clear device list immediately when pairing starts
        const scanResults = document.getElementById('scanResults');
        const deviceList = document.getElementById('deviceList');
        const scanStatus = document.getElementById('scanStatus');
        if (scanResults) {
          scanResults.style.display = 'none';
        }
        if (deviceList) {
          deviceList.innerHTML = '';
        }
        if (scanStatus) {
          scanStatus.innerHTML = '';
        }
        
        // Hide scan card immediately when pairing starts
        const scanCard = document.getElementById('scanCard');
        if (scanCard) {
          scanCard.style.display = 'none';
        }
        
        // Show connecting state on the connect button immediately
        const connectBtn = document.getElementById('quickConnectBtn');
        connectBtn.style.display = 'block';
        connectBtn.disabled = true;
        connectBtn.innerHTML = '<span class="spinner"></span> Connecting...';
        
        try {
          const response = await fetch(`/plugins/bt-tether/pair-device?mac=${encodeURIComponent(mac)}&name=${encodeURIComponent(name)}`, { method: 'GET' });
          const data = await response.json();
          
          if (data.success) {
            showFeedback(`Pairing started with ${name}! Accept the dialog on your phone.`, "success");
            
            // Update MAC input field with the paired device
            macInput.value = mac;
            
            // Scroll to the connection status card
            const phoneConnectionCard = document.getElementById('phoneConnectionCard');
            if (phoneConnectionCard) {
              phoneConnectionCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            
            // Start status polling to show connection progress
            startStatusPolling();
            
            // Reload trusted devices summary
            setTimeout(loadTrustedDevicesSummary, 2000);
            
            // Check connection status to update UI with connect button
            setTimeout(checkConnectionStatus, 1000);
          } else {
            showFeedback(`Pairing failed: ${data.message}`, "error");
            // Reset button on failure
            connectBtn.disabled = false;
            connectBtn.innerHTML = '⚡ Connect to Phone';
          }
        } catch (error) {
          showFeedback(`Pairing failed: ${error.message}`, "error");
          // Reset button on error
          connectBtn.disabled = false;
          connectBtn.innerHTML = '⚡ Connect to Phone';
        }
      }

      async function testInternet() {
        const testBtn = document.getElementById('testInternetBtn');
        const testResults = document.getElementById('testResults');
        const testResultsMessage = document.getElementById('testResultsMessage');
        
        testBtn.disabled = true;
        testBtn.innerHTML = '<span class="spinner"></span> Testing...';
        testResults.style.display = 'block';
        testResultsMessage.className = 'message-box message-info';
        testResultsMessage.innerHTML = '<span class="spinner"></span> Running connectivity tests...';
        
        try {
          const response = await fetch('/plugins/bt-tether/test-internet', { method: 'GET' });
          const data = await response.json();
          
          let resultHtml = '<div style="font-family: monospace; font-size: 13px; line-height: 1.6;">';
          
          // Ping test
          resultHtml += `<div style="margin-bottom: 8px;">`;
          resultHtml += `<b>📡 Ping Test (8.8.8.8):</b> `;
          resultHtml += data.ping_success ? '<span style="color: #28a745;">✓ Success</span>' : '<span style="color: #dc3545;">✗ Failed</span>';
          resultHtml += `</div>`;
          
          // DNS test
          resultHtml += `<div style="margin-bottom: 8px;">`;
          resultHtml += `<b>🔍 DNS Test (google.com):</b> `;
          resultHtml += data.dns_success ? '<span style="color: #28a745;">✓ Success</span>' : '<span style="color: #dc3545;">✗ Failed</span>';
          resultHtml += `</div>`;
          
          // DNS servers
          if (data.dns_servers) {
            resultHtml += `<div style="margin-bottom: 8px; padding-left: 20px; font-size: 12px;">`;
            resultHtml += `<span style="color: #666;">DNS Servers:</span> <span style="color: #0066cc;">${data.dns_servers}</span>`;
            resultHtml += `</div>`;
          }
          
          // DNS error details
          if (!data.dns_success && data.dns_error) {
            resultHtml += `<div style="margin-bottom: 8px; padding-left: 20px; font-size: 11px; background: #fff3cd; padding: 6px; border-radius: 3px;">`;
            resultHtml += `<span style="color: #856404;">Error: ${data.dns_error.substring(0, 150)}...</span>`;
            resultHtml += `</div>`;
          }
          
          // bnep0 IP
          resultHtml += `<div style="margin-bottom: 8px;">`;
          resultHtml += `<b>💻 bnep0 IP:</b> `;
          resultHtml += data.bnep0_ip ? `<span style="color: #28a745;">${data.bnep0_ip}</span>` : '<span style="color: #dc3545;">No IP assigned</span>';
          resultHtml += `</div>`;
          
          // Default route
          resultHtml += `<div style="margin-bottom: 8px;">`;
          resultHtml += `<b>🚦 Default Route:</b> `;
          resultHtml += data.default_route ? `<span style="color: #0066cc;">${data.default_route}</span>` : '<span style="color: #dc3545;">None</span>';
          resultHtml += `</div>`;
          
          // Localhost route - CRITICAL for bettercap API
          resultHtml += `<div style="margin-bottom: 8px;">`;
          resultHtml += `<b>🏠 Localhost Route:</b> `;
          if (data.localhost_routes) {
            const isLoopback = data.localhost_routes.includes('lo') || data.localhost_routes.includes('local');
            const routeColor = isLoopback ? '#28a745' : '#dc3545';
            const routeIcon = isLoopback ? '✓' : '⚠️';
            resultHtml += `<span style="color: ${routeColor};">${routeIcon} ${data.localhost_routes}</span>`;
            if (!isLoopback) {
              resultHtml += `<div style="margin-top: 4px; padding: 6px; background: #fff3cd; border-radius: 3px; font-size: 11px;">`;
              resultHtml += `<span style="color: #856404;">⚠️ WARNING: Localhost not routing through 'lo' interface! This may prevent bettercap API from working.</span>`;
              resultHtml += `</div>`;
            }
          } else {
            resultHtml += '<span style="color: #dc3545;">None</span>';
          }
          resultHtml += `</div>`;
          
          resultHtml += '</div>';
          
          // Set overall result class
          if (data.ping_success && data.dns_success) {
            testResultsMessage.className = 'message-box message-success';
          } else if (data.ping_success || data.dns_success) {
            testResultsMessage.className = 'message-box message-warning';
          } else {
            testResultsMessage.className = 'message-box message-error';
          }
          
          testResultsMessage.innerHTML = resultHtml;
          
        } catch (error) {
          testResultsMessage.className = 'message-box message-error';
          testResultsMessage.textContent = 'Test failed: ' + error.message;
        } finally {
          testBtn.disabled = false;
          testBtn.innerHTML = '🔍 Test Internet Connectivity';
        }
      }

      async function disconnectDevice() {
        const mac = macInput.value.trim();
        if (!/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(mac)) {
          showFeedback("Enter a valid MAC address first", "warning");
          return;
        }
        
        const disconnectBtn = document.getElementById('disconnectBtn');
        const disconnectSection = document.getElementById('disconnectSection');
        const testInternetCard = document.getElementById('testInternetCard');
        
        // Hide the disconnect section immediately to prevent multiple clicks
        disconnectSection.style.display = 'none';
        // Hide internet test card immediately when disconnecting
        testInternetCard.style.display = 'none';
        
        disconnectBtn.disabled = true;
        disconnectBtn.innerHTML = '<span class="spinner"></span> Disconnecting...';
        
        showFeedback("Disconnecting from device...", "info");
        
        try {
          const response = await fetch(`/plugins/bt-tether/disconnect?mac=${encodeURIComponent(mac)}`, { method: 'GET' });
          const data = await response.json();
          
          if (data.success) {
            showFeedback("Device disconnected and removed.", "success");
          }
          
          // Always clear MAC input since disconnect always unpairs the device
          macInput.value = '';
          
          // Update both status displays immediately to show "Disconnecting..."
          await checkConnectionStatus();
          await loadTrustedDevicesSummary();
          
          // Keep polling so the UI updates when disconnect/untrust finishes
          startStatusPolling();
        } catch (error) {
          showFeedback("Disconnect failed: " + error.message, "error");
        } finally {
          disconnectBtn.disabled = false;
          disconnectBtn.innerHTML = '🔌 Disconnect';
        }
      }

      function showFeedback(message, type = "info") {
        // Just log to console since feedback element was removed
        console.log(`[${type.toUpperCase()}] ${message}`);
      }
      
      async function refreshLogs() {
        try {
          const response = await fetch('/plugins/bt-tether/logs');
          const data = await response.json();
          const logContent = document.getElementById('logContent');
          
          // Remember if user is at the bottom before updating
          const isAtBottom = logContent.scrollHeight - logContent.scrollTop <= logContent.clientHeight + 1;
          
          if (data.logs && data.logs.length > 0) {
            logContent.innerHTML = data.logs.map(log => {
              const timestamp = log.timestamp || '';
              const level = (log.level || 'INFO').toUpperCase();
              const message = log.message || '';
              
              let color = '#d4d4d4';
              if (level === 'ERROR') color = '#f48771';
              else if (level === 'WARNING') color = '#dcdcaa';
              else if (level === 'INFO') color = '#4fc1ff';
              else if (level === 'DEBUG') color = '#888';
              
              return `<div><span style=\"color: #888;\">${timestamp}</span> <span style=\"color: ${color}; font-weight: bold;\">[${level}]</span> ${message}</div>`;
            }).join('');
            
            // Only auto-scroll if user was at the bottom, otherwise preserve their scroll position
            if (isAtBottom) {
              logContent.scrollTop = logContent.scrollHeight;
            }
          } else {
            logContent.innerHTML = '<div style=\"color: #888;\">No logs available</div>';
          }
        } catch (error) {
          console.error('Failed to fetch logs:', error);
        }
      }
      
      function startLogPolling() {
        if (logInterval) clearInterval(logInterval);
        // Poll logs every 5 seconds (less aggressive than before)
        logInterval = setInterval(refreshLogs, 5000);
      }
      
      function stopLogPolling() {
        if (logInterval) {
          clearInterval(logInterval);
          logInterval = null;
        }
      }
      
      // Page visibility management - stop polling when page is hidden
      document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
          console.log('Page hidden - stopping all polling');
          stopStatusPolling();
          stopLogPolling();
        } else {
          console.log('Page visible - resuming polling');
          checkConnectionStatus();
          refreshLogs();
          startLogPolling();
        }
      });
      
      // Clean up intervals when page is unloaded
      window.addEventListener('beforeunload', function() {
        console.log('Page unloading - cleaning up');
        stopStatusPolling();
        stopLogPolling();
      });
    </script>
  </body>
</html>
"""


class BTTetherHelper(Plugin):
    __author__ = "wsvdmeer"
    __version__ = "1.2.5"
    __license__ = "GPL3"
    __description__ = "Guided Bluetooth tethering with user instructions"

    # State constants for detailed status display
    STATE_IDLE = "IDLE"
    STATE_INITIALIZING = "INITIALIZING"
    STATE_SCANNING = "SCANNING"
    STATE_PAIRING = "PAIRING"
    STATE_TRUSTING = "TRUSTING"
    STATE_CONNECTING = "CONNECTING"
    STATE_CONNECTED = "CONNECTED"
    STATE_RECONNECTING = "RECONNECTING"
    STATE_DISCONNECTING = "DISCONNECTING"
    STATE_UNTRUSTING = "UNTRUSTING"
    STATE_DISCONNECTED = "DISCONNECTED"
    STATE_ERROR = "ERROR"

    # Bluetooth UUID constants
    NAP_UUID = "00001116-0000-1000-8000-00805f9b34fb"

    # Timing constants
    BLUETOOTH_SERVICE_STARTUP_DELAY = 3
    MONITOR_INITIAL_DELAY = 5
    MONITOR_PAUSED_CHECK_INTERVAL = 10  # Check every 10 seconds when paused
    SCAN_DURATION = 30
    DEVICE_OPERATION_DELAY = 1
    DEVICE_OPERATION_LONGER_DELAY = 2
    SCAN_STOP_DELAY = 0.5
    # Pairing configuration constants
    PAIRING_SCAN_WAIT_TIMEOUT = (
        15  # Max seconds to wait for device to appear in BlueZ cache during pairing
    )
    PAIRING_PASSKEY_TIMEOUT = (
        90  # Max seconds to wait for passkey confirmation on phone
    )
    PAIRING_RETRY_DELAY = 2  # Seconds between pairing retry attempts
    PAIRING_MAX_RETRIES = 2  # Max pairing attempts before giving up
    SCAN_MAC_PATTERN = re.compile(
        r"([0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2})"
    )
    SCAN_ANSI_PATTERN = re.compile(r"(\x1b\[[0-9;]*m|\x08)")
    PROCESS_CLEANUP_DELAY = 0.2
    DBUS_OPERATION_RETRY_DELAY = 0.1
    AGENT_LOG_MONITOR_TIMEOUT = 90  # Seconds to monitor agent log for passkey
    FALLBACK_INIT_TIMEOUT = 15  # Seconds to wait for on_ready() before fallback init
    PAN_INTERFACE_WAIT = 2  # Seconds to wait for PAN interface after connection
    INTERNET_VERIFY_WAIT = 2  # Seconds to wait before verifying internet connectivity
    DHCP_KILL_WAIT = 0.5  # Wait after killing dhclient
    DHCP_RELEASE_WAIT = 1  # Wait after releasing DHCP lease

    # Reconnect configuration constants
    DEFAULT_RECONNECT_INTERVAL = 60  # Default seconds between reconnect checks
    MAX_RECONNECT_FAILURES = 5  # Max consecutive failures before cooldown
    DEFAULT_RECONNECT_FAILURE_COOLDOWN = 300  # Default cooldown in seconds (5 minutes)

    # UI and buffer constants
    UI_LOG_MAXLEN = 100  # Maximum number of log messages in UI buffer

    # Subprocess timeout constants
    SUBPROCESS_TIMEOUT_SHORT = 1  # For quick operations (process cleanup)
    SUBPROCESS_TIMEOUT_MEDIUM = 2  # For moderate operations (network checks)
    SUBPROCESS_TIMEOUT_NORMAL = 3  # For standard operations (minor bluetoothctl)
    SUBPROCESS_TIMEOUT_STANDARD = 5  # For main bluetoothctl operations
    SUBPROCESS_TIMEOUT_LONG = 10  # For long-running operations (device removal)

    # UI polling intervals (milliseconds)
    UI_STATUS_POLL_INTERVAL = 2000  # Connection status check interval
    UI_LOG_POLL_INTERVAL = 5000  # Log refresh interval

    # Operation delay constants
    OPERATION_SHORT_DELAY = 0.5  # General short delay between operations
    OPERATION_MEDIUM_DELAY = 3  # Medium delay for settlement/hardware stabilization

    # Internal plugin flag - not a user-configurable option
    csrf_exempt = True

    def on_loaded(self):
        """Initialize plugin configuration and data structures only - no heavy operations"""
        from collections import deque

        self.phone_mac = ""
        self._status = self.STATE_IDLE
        self._message = "Ready"
        self._scanning = False
        self._stop_scan = False
        self._last_scan_devices = []
        self._discovered_devices = {}
        self._scan_complete_time = 0
        self.lock = threading.Lock()
        self.agent_process = None
        self.agent_log_fd = None
        self.agent_log_path = None
        self.current_passkey = None

        self._ui_logs = deque(maxlen=self.UI_LOG_MAXLEN)
        self._ui_log_lock = threading.Lock()

        self.show_on_screen = self.options.get("show_on_screen", True)
        self.show_mini_status = self.options.get("show_mini_status", True)
        self.mini_status_position = self.options.get("mini_status_position", [110, 0])
        self.show_detailed_status = self.options.get("show_detailed_status", True)
        self.detailed_status_position = self.options.get(
            "detailed_status_position", [0, 82]
        )
        self.auto_reconnect = self.options.get("auto_reconnect", True)
        self.reconnect_interval = self.options.get(
            "reconnect_interval", self.DEFAULT_RECONNECT_INTERVAL
        )

        self._bluetoothctl_lock = threading.Lock()

        self._connection_in_progress = False
        self._connection_start_time = None
        self._disconnecting = False
        self._disconnect_start_time = None
        self._untrusting = False
        self._untrust_start_time = None
        self._initializing = True

        self.OPERATION_TIMEOUT = 120

        self._monitor_thread = None
        self._monitor_stop = threading.Event()
        self._monitor_paused = threading.Event()
        self._last_known_connected = False
        self._reconnect_failure_count = 0
        self._max_reconnect_failures = self.MAX_RECONNECT_FAILURES
        self._reconnect_failure_cooldown = self.options.get(
            "reconnect_failure_cooldown", self.DEFAULT_RECONNECT_FAILURE_COOLDOWN
        )
        self._first_failure_time = None
        self._user_requested_disconnect = False

        self._screen_needs_refresh = False

        # Cached UI status - updated by background threads, read by on_ui_update
        # This prevents blocking subprocess calls during UI updates
        self._cached_ui_status = {
            "paired": False,
            "trusted": False,
            "connected": False,
            "pan_active": False,
            "interface": None,
            "ip_address": None,
        }
        self._cached_ui_status_lock = threading.Lock()
        self._ui_reference = None

        self._initialization_done = threading.Event()
        self._fallback_thread = None
        self._last_known_pan_active = False

        self._log("INFO", "Plugin configuration loaded")

        # Start fallback initialization thread in case on_ready() is never called
        self._fallback_thread = threading.Thread(
            target=self._fallback_initialization, daemon=True
        )
        self._fallback_thread.start()

    def _fallback_initialization(self):
        """Fallback initialization if on_ready() is not called within timeout"""
        if not self._initialization_done.wait(timeout=self.FALLBACK_INIT_TIMEOUT):
            self._log(
                "WARNING", "on_ready() was not called, using fallback initialization"
            )
            if not self._initialization_done.is_set():
                self._initialization_done.set()
                self._initialize_bluetooth_services()

    def on_ready(self, agent):
        """Called when everything is ready and the main loop is about to start"""
        self._log("INFO", "on_ready() called, initializing Bluetooth services...")
        if not self._initialization_done.is_set():
            self._initialization_done.set()
            self._initialize_bluetooth_services()

    def _initialize_bluetooth_services(self):
        """Initialize Bluetooth services - called by either on_ready() or fallback"""
        with self.lock:
            self._initializing = True
            self._screen_needs_refresh = True

        try:
            try:
                subprocess.run(
                    ["pkill", "-9", "bluetoothctl"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._log("INFO", "Cleaned up lingering bluetoothctl processes")
            except Exception as e:
                self._log("DEBUG", f"Process cleanup: {e}")

            # Restart bluetooth service to ensure clean state
            try:
                self._log("INFO", "Restarting Bluetooth service...")
                subprocess.run(
                    ["systemctl", "restart", "bluetooth"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                )
                time.sleep(self.BLUETOOTH_SERVICE_STARTUP_DELAY)
                self._log("INFO", "Bluetooth service restarted")
            except Exception as e:
                self._log("WARNING", f"Failed to restart Bluetooth service: {e}")

            # Verify localhost routing is intact (critical for bettercap API)
            try:
                self._verify_localhost_route()
            except Exception as e:
                self._log("WARNING", f"Initial localhost check failed: {e}")

            self._start_pairing_agent()

            if self.auto_reconnect:
                self._start_monitoring_thread()

            self._set_device_name()

            self._log("INFO", "Bluetooth services initialized")

            if self.auto_reconnect:
                self._log("INFO", "Checking for trusted devices to auto-connect...")
                best_device = self._find_best_device_to_connect(log_results=False)
                if best_device:
                    self._log(
                        "INFO",
                        f"Found trusted device: {best_device['name']}, starting connection...",
                    )
                    self._update_cached_ui_status(mac=best_device["mac"])

                    with self.lock:
                        self._connection_in_progress = True
                        self._connection_start_time = time.time()
                        self._user_requested_disconnect = False
                        self.phone_mac = best_device["mac"]
                        self._initializing = False
                        self.status = self.STATE_CONNECTING
                        self.message = f"Auto-connecting to {best_device['name']}..."
                        self._screen_needs_refresh = True
                    self._log(
                        "INFO",
                        f"Initialization complete (auto-connect starting) - initializing flag cleared: {not self._initializing}",
                    )

                    self._monitor_paused.clear()
                    threading.Thread(
                        target=self._connect_thread, args=(best_device,), daemon=True
                    ).start()
                else:
                    self._log(
                        "INFO", "No trusted devices found. Pair a device via web UI."
                    )
                    # Update cached UI status to show no device
                    self._update_cached_ui_status(
                        status={
                            "paired": False,
                            "trusted": False,
                            "connected": False,
                            "pan_active": False,
                            "interface": None,
                            "ip_address": None,
                        }
                    )
                    # No device to connect, end initialization AFTER cache update
                    with self.lock:
                        self._initializing = False
                        self._screen_needs_refresh = True

                    # Force immediate screen update by calling on_ui_update if UI reference available
                    if self._ui_reference:
                        try:
                            self.on_ui_update(self._ui_reference)
                        except Exception as e:
                            logging.debug(
                                f"[bt-tether] Error forcing UI update after init: {e}"
                            )
                    self._log(
                        "INFO",
                        f"Initialization complete - initializing flag cleared: {not self._initializing}",
                    )
            else:
                # Auto-reconnect disabled, update cached UI then end initialization
                self._update_cached_ui_status()
                with self.lock:
                    self._initializing = False
                    self._screen_needs_refresh = True
                self._log(
                    "INFO",
                    f"Initialization complete (auto-reconnect disabled) - initializing flag cleared: {not self._initializing}",
                )

                # Force immediate screen update by calling on_ui_update if UI reference available
                if self._ui_reference:
                    try:
                        self.on_ui_update(self._ui_reference)
                    except Exception as e:
                        logging.debug(
                            f"[bt-tether] Error forcing UI update after init: {e}"
                        )
        except Exception as e:
            self._log("ERROR", f"Failed to initialize Bluetooth services: {e}")
            # Update cached UI to show current state
            self._update_cached_ui_status()
            with self.lock:
                self._initializing = (
                    False  # Mark initialization as complete even on error
                )
                self._screen_needs_refresh = True
            self._log(
                "INFO",
                f"Initialization error handler - initializing flag cleared: {not self._initializing}",
            )
            self._log("ERROR", f"Traceback: {traceback.format_exc()}")

            # Force immediate screen update by calling on_ui_update if UI reference available
            if self._ui_reference:
                try:
                    self.on_ui_update(self._ui_reference)
                except Exception as update_error:
                    logging.debug(
                        f"[bt-tether] Error forcing UI update after init error: {update_error}"
                    )

    def on_unload(self, ui):
        """Cleanup when plugin is unloaded"""
        try:
            self._log("INFO", "Unloading plugin, cleaning up resources...")

            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_stop.set()
                self._monitor_thread.join(timeout=self.SUBPROCESS_TIMEOUT_STANDARD)

            if self.agent_process and self.agent_process.poll() is None:
                try:
                    self.agent_process.terminate()
                    self.agent_process.wait(timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
                except subprocess.TimeoutExpired:
                    logging.warning("[bt-tether] Agent didn't terminate, killing...")
                    try:
                        self.agent_process.kill()
                        self.agent_process.wait(timeout=self.SUBPROCESS_TIMEOUT_SHORT)
                    except Exception as kill_err:
                        logging.error(f"[bt-tether] Agent kill failed: {kill_err}")
                except Exception as e:
                    logging.debug(f"[bt-tether] Agent terminate failed: {e}")

            if self.agent_log_fd:
                try:
                    if isinstance(self.agent_log_fd, int):
                        os.close(self.agent_log_fd)
                    else:
                        self.agent_log_fd.close()
                    self.agent_log_fd = None
                except Exception as e:
                    logging.debug(f"[bt-tether] Failed to close agent log: {e}")

            if self.agent_log_path and os.path.exists(self.agent_log_path):
                try:
                    os.remove(self.agent_log_path)
                except Exception as e:
                    logging.debug(f"[bt-tether] Failed to remove agent log: {e}")

            self._log("INFO", "Plugin unloaded successfully")
        except Exception as e:
            logging.error(f"[bt-tether] Error during unload: {e}")

    def _log(self, level, message):
        """Log to both system logger and UI log buffer"""
        full_message = f"[bt-tether] {message}"
        level_upper = level.upper()
        if level_upper == "ERROR":
            logging.error(full_message)
        elif level_upper == "WARNING":
            logging.warning(full_message)
        elif level_upper == "DEBUG":
            logging.debug(full_message)
        else:
            logging.info(full_message)

        with self._ui_log_lock:
            self._ui_logs.append(
                {
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                    "level": level_upper,
                    "message": message,
                }
            )

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def message(self):
        return self._message

    @message.setter
    def message(self, value):
        self._message = value

    def _set_state(self, status, message, **kwargs):
        """Update plugin state atomically under lock and trigger screen refresh.

        Sets status, message, _screen_needs_refresh=True, and any extra attributes
        passed as keyword arguments (e.g. _connection_in_progress=False).
        """
        with self.lock:
            self.status = status
            self.message = message
            for key, value in kwargs.items():
                setattr(self, key, value)
            self._screen_needs_refresh = True

    def _emit_event(self, event_name, event_data):
        """Emit a custom event to other plugins"""
        try:
            self._log("DEBUG", f"_emit_event() called: {event_name}")
            event_data.setdefault("pwnagotchi_name", self._get_pwnagotchi_name())

            self._log("DEBUG", f"Calling plugins.on() for event: {event_name}")
            plugins.on(event_name, None, event_data)
            self._log("DEBUG", f"Event emitted: {event_name}")
            for key, value in event_data.items():
                self._log("DEBUG", f"  • {key}: {value}")
        except Exception as e:
            self._log("WARNING", f"Failed to emit event {event_name}: {e}")
            self._log("WARNING", f"Traceback: {traceback.format_exc()}")

    def on_ui_setup(self, ui):
        """Setup UI elements to display Bluetooth status on screen"""
        self._ui_reference = ui

        if self.show_on_screen and self.show_mini_status:
            pos = (
                tuple(self.mini_status_position)
                if isinstance(self.mini_status_position, (list, tuple))
                else self.mini_status_position
            )

            ui.add_element(
                "bt-status",
                LabeledValue(
                    color=BLACK,
                    label="BT",
                    value="D",
                    position=pos,
                    label_font=fonts.Bold,
                    text_font=fonts.Medium,
                ),
            )

        if self.show_on_screen and self.show_detailed_status:
            ui.add_element(
                "bt-detail",
                LabeledValue(
                    color=BLACK,
                    label="",
                    value="BT:--",
                    position=tuple(self.detailed_status_position),
                    label_font=fonts.Small,
                    text_font=fonts.Small,
                ),
            )

    def on_ui_update(self, ui):
        """Update Bluetooth status on screen - MUST be non-blocking"""
        if not self.show_on_screen:
            return

        try:
            with self.lock:
                initializing = self._initializing
                connection_in_progress = self._connection_in_progress
                connection_start_time = self._connection_start_time
                disconnecting = self._disconnecting
                disconnect_start_time = self._disconnect_start_time
                untrusting = self._untrusting
                untrust_start_time = self._untrust_start_time
                phone_mac = self.phone_mac
                screen_needs_refresh = self._screen_needs_refresh
                status_str = self.status
                message_str = self.message
                scanning = self._scanning
                if screen_needs_refresh:
                    self._screen_needs_refresh = False

            if initializing:
                logging.debug(
                    f"[bt-tether] on_ui_update() - initializing flag is TRUE, screen_needs_refresh={screen_needs_refresh}"
                )
            else:
                logging.debug(
                    f"[bt-tether] on_ui_update() - initializing flag is FALSE, will show status: {status_str}"
                )

            with self._cached_ui_status_lock:
                cached_status = self._cached_ui_status.copy()

            current_time = time.time()

            if connection_in_progress and connection_start_time:
                if current_time - connection_start_time > self.OPERATION_TIMEOUT:
                    logging.warning(
                        f"[bt-tether] Connection timeout ({self.OPERATION_TIMEOUT}s) - clearing stuck flag"
                    )
                    with self.lock:
                        self._connection_in_progress = False
                        self._connection_start_time = None
                        self.status = self.STATE_ERROR
                        self.message = "Connection timeout - operation took too long"
                        self._screen_needs_refresh = True
                    self._update_cached_ui_status()
                    connection_in_progress = False

            if disconnecting and disconnect_start_time:
                if current_time - disconnect_start_time > self.OPERATION_TIMEOUT:
                    logging.warning(
                        f"[bt-tether] Disconnect timeout ({self.OPERATION_TIMEOUT}s) - clearing stuck flag"
                    )
                    with self.lock:
                        self._disconnecting = False
                        self._disconnect_start_time = None
                    disconnecting = False

            if untrusting and untrust_start_time:
                if current_time - untrust_start_time > self.OPERATION_TIMEOUT:
                    logging.warning(
                        f"[bt-tether] Untrust timeout ({self.OPERATION_TIMEOUT}s) - clearing stuck flag"
                    )
                    with self.lock:
                        self._untrusting = False
                        self._untrust_start_time = None
                    untrusting = False

            if initializing:
                if self.show_mini_status:
                    ui.set("bt-status", "I")
                if self.show_detailed_status:
                    ui.set("bt-detail", "BT:Initializing")
                return

            if scanning:
                if self.show_mini_status:
                    ui.set("bt-status", "S")
                if self.show_detailed_status:
                    ui.set("bt-detail", "BT:Scanning")
                return

            if disconnecting:
                if self.show_mini_status:
                    ui.set("bt-status", "D")
                if self.show_detailed_status:
                    ui.set("bt-detail", "BT:Disconnecting")
                return

            if untrusting:
                if self.show_mini_status:
                    ui.set("bt-status", "T")
                if self.show_detailed_status:
                    ui.set("bt-detail", "BT:Untrusting")
                return

            if connection_in_progress:
                if status_str == self.STATE_CONNECTED:
                    pass
                elif status_str == self.STATE_PAIRING:
                    if self.show_mini_status:
                        ui.set("bt-status", "P")
                    if self.show_detailed_status:
                        ui.set("bt-detail", "BT:Pairing")
                    return
                elif status_str == self.STATE_TRUSTING:
                    if self.show_mini_status:
                        ui.set("bt-status", "T")
                    if self.show_detailed_status:
                        ui.set("bt-detail", "BT:Trusting")
                    return
                elif status_str == self.STATE_CONNECTING:
                    if self.show_mini_status:
                        ui.set("bt-status", ">")
                    if self.show_detailed_status:
                        ui.set("bt-detail", "BT:Connecting")
                    return
                elif status_str == self.STATE_RECONNECTING:
                    if cached_status.get("connected") or cached_status.get(
                        "pan_active"
                    ):
                        pass
                    else:
                        if self.show_mini_status:
                            ui.set("bt-status", "R")
                        if self.show_detailed_status:
                            ui.set("bt-detail", "BT:Reconnecting")
                        return
                else:
                    if self.show_mini_status:
                        ui.set("bt-status", ">")
                    if self.show_detailed_status:
                        ui.set("bt-detail", "BT:Connecting")
                    return

            if not phone_mac and not cached_status.get("paired", False):
                if self.show_mini_status:
                    ui.set("bt-status", "X")
                if self.show_detailed_status:
                    ui.set("bt-detail", "BT:No device")
                return

            if cached_status.get("pan_active", False):
                display = "C"
            elif cached_status.get("connected", False) and cached_status.get(
                "trusted", False
            ):
                display = "T"
            elif cached_status.get("connected", False):
                display = "N"
            elif cached_status.get("paired", False):
                display = "P"
            else:
                display = "X"

            if self.show_mini_status:
                ui.set("bt-status", display)

            if self.show_detailed_status:
                try:
                    detailed = self._format_detailed_status(cached_status)
                    ui.set("bt-detail", detailed)
                except Exception as detail_error:
                    logging.debug(f"[bt-tether] Detailed status error: {detail_error}")
                    ui.set("bt-detail", f"BT:{display}")

        except Exception as e:
            logging.debug(f"[bt-tether] UI update error: {e}")
            try:
                if self.show_mini_status:
                    ui.set("bt-status", "?")
                if self.show_detailed_status:
                    ui.set("bt-detail", "BT:Error")
            except Exception as ui_err:
                logging.debug(f"[bt-tether] Failed to set error UI: {ui_err}")

    def _format_detailed_status(self, status):
        """Format detailed status line for screen display"""
        with self.lock:
            disconnecting = self._disconnecting
            connection_in_progress = self._connection_in_progress
            untrusting = self._untrusting

        connected = status.get("connected", False)
        paired = status.get("paired", False)
        trusted = status.get("trusted", False)
        pan_active = status.get("pan_active", False)
        ip_address = status.get("ip_address", None)

        with self.lock:
            status_str = self.status

        if disconnecting:
            return "BT:Disconnecting..."
        elif untrusting:
            return "BT:Untrusting..."
        elif connection_in_progress:
            if status_str == self.STATE_CONNECTED:
                pass
            elif status_str == self.STATE_RECONNECTING:
                return "BT:Reconnecting..."
            else:
                return "BT:Connecting..."

        if pan_active:
            if ip_address:
                return f"BT:{ip_address}"
            else:
                return "BT:Connected"
        elif connected and trusted:
            return "BT:Trusted"
        elif connected:
            return "BT:Connected"
        elif paired:
            return "BT:Paired"
        else:
            return "BT:Disconnected"

    def _update_cached_ui_status(self, status=None, mac=None):
        """Update the cached UI status from a background thread"""
        try:
            if status is None:
                target_mac = mac if mac else self.phone_mac
                if target_mac:
                    status = self._get_current_status(target_mac)
                else:
                    status = {
                        "paired": False,
                        "trusted": False,
                        "connected": False,
                        "pan_active": False,
                        "interface": None,
                        "ip_address": None,
                    }

            with self._cached_ui_status_lock:
                self._cached_ui_status = status.copy()

            with self.lock:
                self._screen_needs_refresh = True

        except Exception as e:
            logging.debug(f"[bt-tether] Failed to update cached UI status: {e}")

    def _start_pairing_agent(self):
        """Start a persistent bluetoothctl agent to handle pairing requests"""
        try:
            if self.agent_process and self.agent_process.poll() is None:
                self._log("INFO", "Pairing agent already running")
                return

            self._log("INFO", "Starting persistent pairing agent...")

            agent_commands = """power on
agent KeyboardDisplay
default-agent
"""

            env = dict(os.environ)
            env["NO_COLOR"] = "1"
            env["TERM"] = "dumb"

            import tempfile

            self.agent_log_fd, self.agent_log_path = tempfile.mkstemp(
                prefix="bt-agent-", suffix=".log"
            )
            logging.info(
                f"[bt-tether] Agent output will be logged to: {self.agent_log_path}"
            )

            self.agent_process = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=self.agent_log_fd,
                stderr=self.agent_log_fd,
                text=False,
                env=env,
            )

            try:
                self.agent_process.stdin.write(agent_commands.encode())
                self.agent_process.stdin.flush()
            except BrokenPipeError:
                self._log(
                    "WARNING",
                    "Agent process stdin pipe broken - process may have exited",
                )
                return

            logging.info(
                "[bt-tether] ✓ Persistent pairing agent started (KeyboardDisplay mode - passkey will be shown)"
            )
            logging.info(
                f"[bt-tether] 🔑 Passkeys will appear in: {self.agent_log_path}"
            )
        except Exception as e:
            logging.error(f"[bt-tether] Failed to start pairing agent: {e}")
            if self.agent_log_fd:
                try:
                    os.close(self.agent_log_fd)
                except:
                    pass
                self.agent_log_fd = None
            if self.agent_log_path and os.path.exists(self.agent_log_path):
                try:
                    os.remove(self.agent_log_path)
                except:
                    pass
                self.agent_log_path = None

    def _start_monitoring_thread(self):
        """Start background thread to monitor connection and auto-reconnect if dropped"""
        try:
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._log("INFO", "Monitoring thread already running")
                return

            self._monitor_stop.clear()
            self._monitor_thread = threading.Thread(
                target=self._connection_monitor_loop, daemon=True
            )
            self._monitor_thread.start()
            self._log(
                "INFO",
                f"Started connection monitoring (interval: {self.reconnect_interval}s)",
            )
        except Exception as e:
            logging.error(f"[bt-tether] Failed to start monitoring thread: {e}")

    def _connection_monitor_loop(self):
        """Background loop to monitor connection status and reconnect if needed"""
        logging.info("[bt-tether] Connection monitor started")

        time.sleep(self.MONITOR_INITIAL_DELAY)

        while not self._monitor_stop.is_set():
            try:
                with self.lock:
                    connection_in_progress = self._connection_in_progress

                if connection_in_progress:
                    time.sleep(self.reconnect_interval)
                    continue

                best_device = self._find_best_device_to_connect(log_results=False)

                if not best_device:
                    if not self._monitor_paused.is_set():
                        self._log(
                            "INFO", "No trusted devices to monitor. Monitor paused."
                        )
                        self._monitor_paused.set()

                    time.sleep(self.reconnect_interval)
                    continue

                current_mac = best_device["mac"]
                device_name = best_device["name"]

                if self._monitor_paused.is_set():
                    self._monitor_paused.clear()
                    logging.info(
                        f"[bt-tether] Monitor resumed - found device: {device_name}"
                    )

                status = self._get_full_connection_status(current_mac)
                self._update_cached_ui_status(status=status, mac=current_mac)

                if not status["connected"]:
                    self._log(
                        "DEBUG", f"Monitoring device: {device_name} ({current_mac})"
                    )

                pan_active = status.get("pan_active", False)
                self._last_known_pan_active = pan_active

                with self.lock:
                    user_requested_disconnect = self._user_requested_disconnect

                if (
                    self._last_known_connected
                    and not status["connected"]
                    and not user_requested_disconnect
                ):
                    logging.warning(
                        f"[bt-tether] Connection to {device_name} dropped! Attempting to reconnect..."
                    )

                    event_data = {
                        "mac": current_mac,
                        "device": device_name,
                        "reason": "connection_dropped",
                    }
                    self._emit_event("bt_tether_disconnected", event_data)
                    self._log(
                        "INFO", f"Event emitted: device disconnected - {device_name}"
                    )

                    with self.lock:
                        self.status = self.STATE_DISCONNECTED
                        self.message = f"Connection to {device_name} dropped"
                        self._screen_needs_refresh = True

                    self._update_cached_ui_status(
                        status={
                            "paired": True,
                            "trusted": True,
                            "connected": False,
                            "pan_active": False,
                            "interface": None,
                            "ip_address": None,
                        },
                        mac=current_mac,
                    )

                    with self.lock:
                        self.status = self.STATE_RECONNECTING
                        self.message = (
                            f"Connection lost to {device_name}, reconnecting..."
                        )
                        self._connection_in_progress = True
                        self._connection_start_time = time.time()
                        self._initializing = False
                        self._screen_needs_refresh = True

                    # Attempt to reconnect to this device
                    success = self._reconnect_device()

                    if success:
                        # Update phone_mac to the device we successfully connected to
                        self.phone_mac = current_mac
                        self.options["mac"] = self.phone_mac
                        # Mark as connected so we don't trigger the second reconnect block
                        self._last_known_connected = True
                        self._reconnect_failure_count = 0
                        self._first_failure_time = None
                    else:
                        # Reconnection failed - update last known state to disconnected
                        self._last_known_connected = False
                        self._reconnect_failure_count += 1
                        if self._first_failure_time is None:
                            self._first_failure_time = time.time()
                        if (
                            self._reconnect_failure_count
                            >= self._max_reconnect_failures
                        ):
                            self._log(
                                "WARNING",
                                f"⚠️  Auto-reconnect paused after {self._max_reconnect_failures} failed attempts",
                            )
                            self._log(
                                "INFO",
                                f"📱 Will retry after {self._reconnect_failure_cooldown}s cooldown, or reconnect manually via web UI",
                            )
                            with self.lock:
                                self.status = self.STATE_DISCONNECTED
                                self.message = f"Auto-reconnect paused - retrying in {self._reconnect_failure_cooldown}s"
                                self._connection_in_progress = (
                                    False  # Clear flag to show proper status
                                )
                                self._screen_needs_refresh = True

                    # Skip the rest of this iteration - we already handled reconnection
                    # Using stale `status` below would cause a double-reconnect attempt
                    time.sleep(self.reconnect_interval)
                    continue

                # Force screen refresh if connection state changed
                if self._last_known_connected != status["connected"]:
                    with self.lock:
                        self._screen_needs_refresh = True

                # Update last known state (do this AFTER checking for changes)
                self._last_known_connected = status["connected"]

                # Only try to reconnect if device is BOTH paired AND trusted (and not blocked)
                # Also check if we haven't exceeded max failures and user didn't manually disconnect
                with self.lock:
                    connection_in_progress = self._connection_in_progress
                    user_requested_disconnect = self._user_requested_disconnect

                if (
                    status["paired"]
                    and status["trusted"]
                    and not status["connected"]
                    and not connection_in_progress
                    and self._reconnect_failure_count < self._max_reconnect_failures
                    and not user_requested_disconnect
                ):
                    logging.info(
                        f"[bt-tether] Device {device_name} is paired/trusted but not connected. Attempting connection..."
                    )
                    with self.lock:
                        self.status = self.STATE_CONNECTING
                        self.message = f"Reconnecting to {device_name}..."
                        self._connection_in_progress = True
                        self._connection_start_time = time.time()
                        self._initializing = (
                            False  # Ensure initializing flag is cleared
                        )
                        self._screen_needs_refresh = True

                    # Update cached UI to show disconnected immediately before reconnecting
                    # This ensures the UI shows the transition through the connecting state
                    self._update_cached_ui_status(status=status, mac=current_mac)

                    success = self._reconnect_device()

                    if success:
                        # Reset failure counter on successful connection
                        self._reconnect_failure_count = 0
                        self._first_failure_time = None
                        # Update phone_mac to the successful device
                        self.phone_mac = current_mac
                        self.options["mac"] = self.phone_mac
                        # Update last known state so next iteration doesn't re-trigger
                        self._last_known_connected = True
                    else:
                        # Increment failure counter
                        self._reconnect_failure_count += 1
                        # Track when failures started
                        if self._first_failure_time is None:
                            self._first_failure_time = time.time()
                        # Update cached UI to show disconnected state after failure
                        self._update_cached_ui_status(mac=current_mac)
                        if (
                            self._reconnect_failure_count
                            >= self._max_reconnect_failures
                        ):
                            self._log(
                                "WARNING",
                                f"⚠️  Auto-reconnect paused after {self._max_reconnect_failures} failed attempts",
                            )
                            self._log(
                                "INFO",
                                f"📱 Will retry after {self._reconnect_failure_cooldown}s cooldown, or reconnect manually via web UI",
                            )
                            with self.lock:
                                self.status = self.STATE_DISCONNECTED
                                self.message = f"Auto-reconnect paused - retrying in {self._reconnect_failure_cooldown}s"
                                self._connection_in_progress = (
                                    False  # Clear flag to show proper status
                                )
                                self._screen_needs_refresh = True
                elif self._reconnect_failure_count >= self._max_reconnect_failures:
                    # Already exceeded max failures - check if cooldown period has elapsed
                    if self._first_failure_time:
                        time_since_first_failure = (
                            time.time() - self._first_failure_time
                        )
                        if time_since_first_failure >= self._reconnect_failure_cooldown:
                            # Cooldown period elapsed, reset counter and try again
                            self._log(
                                "INFO",
                                f"Cooldown period elapsed ({self._reconnect_failure_cooldown}s), resetting failure counter and retrying...",
                            )
                            self._reconnect_failure_count = 0
                            self._first_failure_time = None
                elif not status["paired"] or not status["trusted"]:
                    # Device not paired/trusted (or blocked), don't attempt auto-reconnect
                    # Reset failure counter since this is intentional
                    self._reconnect_failure_count = 0
                    self._first_failure_time = None
                    logging.debug(
                        f"[bt-tether] Device not ready for auto-reconnect (paired={status['paired']}, trusted={status['trusted']})"
                    )

            except Exception as e:
                logging.error(f"[bt-tether] Monitor loop error: {e}")

            # Wait for next check
            time.sleep(self.reconnect_interval)

        logging.info("[bt-tether] Connection monitor stopped")

    def _reconnect_device(self):
        """Attempt to reconnect to a previously paired device"""
        try:
            # Find best device if no MAC is set
            if not self.phone_mac:
                best_device = self._find_best_device_to_connect()
                if not best_device:
                    self._log("DEBUG", "No trusted devices found for reconnection")
                    return False
                mac = best_device["mac"]
                self.phone_mac = mac
            else:
                mac = self.phone_mac

            with self.lock:
                self._connection_in_progress = True
                self._connection_start_time = time.time()
                self._initializing = False

            self._log("INFO", f"Reconnecting to {mac}...")

            # Check if device is blocked
            devices_output = self._run_cmd(
                ["bluetoothctl", "devices", "Blocked"],
                capture=True,
                timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
            )
            if devices_output and devices_output != "Timeout" and mac in devices_output:
                self._log("INFO", f"Unblocking device {mac}...")
                self._run_cmd(["bluetoothctl", "unblock", mac], capture=True)
                time.sleep(self.DEVICE_OPERATION_DELAY)

            # Trust the device
            self._log("INFO", f"Ensuring device is trusted...")
            self._run_cmd(["bluetoothctl", "trust", mac], capture=True)
            time.sleep(self.DEVICE_OPERATION_DELAY)

            # Try NAP connection (this will also establish Bluetooth connection if needed)
            self._log("INFO", f"Attempting NAP connection...")
            nap_connected = self._connect_nap_dbus(mac)

            if nap_connected:
                self._log("INFO", f"✓ Reconnection successful")

                # Wait for PAN interface
                time.sleep(self.PAN_INTERFACE_WAIT)

                # Check if PAN interface is up
                if self._pan_active():
                    iface = self._get_pan_interface()
                    self._log("INFO", f"✓ PAN interface active: {iface}")

                    # Setup network with DHCP
                    if self._setup_network_dhcp(iface):
                        self._log("INFO", f"✓ Network setup successful")

                    # Verify internet connectivity
                    time.sleep(self.INTERNET_VERIFY_WAIT)
                    if self._check_internet_connectivity():
                        self._log("INFO", f"✓ Internet connectivity verified!")

                        # Update cached UI status FIRST while flag is still True
                        self._update_cached_ui_status(mac=mac)

                        # Emit connected event (mirrors original Discord notification trigger)
                        self._emit_event(
                            "bt_tether_connected",
                            {
                                "mac": mac,
                                "device": mac,
                                "ip": self._get_current_ip() or "unknown",
                                "interface": iface,
                            },
                        )

                        # Then update status and clear flags
                        with self.lock:
                            self.status = self.STATE_CONNECTED
                            self.message = f"✓ Reconnected! Internet via {iface}"
                            self._connection_in_progress = False
                            self._connection_start_time = None
                            self._initializing = False
                            self._screen_needs_refresh = True
                        return True
                    else:
                        logging.warning(
                            f"[bt-tether] Reconnected but no internet detected"
                        )
                        # Update cached UI status FIRST while flag is still True
                        self._update_cached_ui_status(mac=mac)

                        # Then update status and clear flags
                        with self.lock:
                            self.status = self.STATE_CONNECTED
                            self.message = f"Reconnected via {iface} but no internet"
                            self._connection_in_progress = False
                            self._connection_start_time = None
                            self._initializing = False
                            self._screen_needs_refresh = True
                        return True
                else:
                    logging.warning(
                        f"[bt-tether] NAP connected but no interface detected"
                    )
                    # Update cached UI status FIRST while flag is still True
                    self._update_cached_ui_status(mac=mac)

                    # Then update status and clear flags
                    with self.lock:
                        self.status = self.STATE_CONNECTED
                        self.message = "Reconnected but no PAN interface"
                        self._connection_in_progress = False
                        self._connection_start_time = None
                        self._initializing = False
                        self._screen_needs_refresh = True
                    return True
            else:
                logging.warning(f"[bt-tether] Reconnection failed")
                self._set_state(
                    self.STATE_DISCONNECTED,
                    "Reconnection failed. Will retry later.",
                    _connection_in_progress=False,
                    _connection_start_time=None,
                    _initializing=False,
                )
                # Force cached UI to show disconnected (clear any lingering IP/interface)
                self._update_cached_ui_status(
                    status={
                        "paired": True,
                        "trusted": True,
                        "connected": False,
                        "pan_active": False,
                        "interface": None,
                        "ip_address": None,
                    },
                    mac=mac,
                )
                return False

        except Exception as e:
            logging.error(f"[bt-tether] Reconnection error: {e}")
            self._set_state(
                self.STATE_DISCONNECTED,
                f"Reconnection error: {str(e)[:50]}",
                _connection_in_progress=False,
                _connection_start_time=None,
                _initializing=False,
            )
            # Force cached UI to show disconnected (clear any lingering IP/interface)
            self._update_cached_ui_status(
                status={
                    "paired": True,
                    "trusted": True,
                    "connected": False,
                    "pan_active": False,
                    "interface": None,
                    "ip_address": None,
                },
                mac=mac,
            )
            return False
        finally:
            # Ensure flag is cleared
            with self.lock:
                if self._connection_in_progress:
                    self._connection_in_progress = False

    def _monitor_agent_log_for_passkey(self, passkey_found_event):
        """Monitor agent log file for passkey display in real-time and auto-confirm"""
        try:
            import time

            logging.info("[bt-tether] Monitoring agent log for passkey...")

            # Tail the agent log file
            with open(self.agent_log_path, "r") as f:
                # Seek to end of file
                f.seek(0, 2)

                # Monitor for configured timeout
                start_time = time.time()
                last_prompt = None
                while time.time() - start_time < self.AGENT_LOG_MONITOR_TIMEOUT:
                    # Exit early if passkey found
                    if passkey_found_event.is_set():
                        logging.info("[bt-tether] Passkey found, stopping log monitor")
                        break

                    line = f.readline()
                    if line:
                        clean_line = self._strip_ansi_codes(line.strip())
                        if clean_line:
                            # Look for passkey or confirmation request
                            if (
                                "passkey" in clean_line.lower()
                                or "confirm passkey" in clean_line.lower()
                            ):
                                # Extract passkey number (usually 6 digits)

                                passkey_match = re.search(
                                    r"passkey\s+(\d{6})", clean_line, re.IGNORECASE
                                )
                                if passkey_match:
                                    self.current_passkey = passkey_match.group(1)
                                    self._log(
                                        "WARNING",
                                        f"🔑 PASSKEY: {self.current_passkey} - Confirm on phone!",
                                    )
                                    logging.info(
                                        f"[bt-tether] 🔑 PASSKEY: {self.current_passkey} captured from agent log"
                                    )

                                    # Update status message so it shows prominently in web UI
                                    with self.lock:
                                        self.status = self.STATE_PAIRING
                                        self.message = f"🔑 PASSKEY: {self.current_passkey}\n\nVerify this matches on your phone, then tap PAIR!"

                                    # Auto-confirm passkey on Pwnagotchi side
                                    if (
                                        self.agent_process
                                        and self.agent_process.poll() is None
                                    ):
                                        try:
                                            self._log(
                                                "INFO",
                                                "✅ Auto-confirming on Pwnagotchi & waiting for phone...",
                                            )
                                            if (
                                                self.agent_process.stdin
                                                and not self.agent_process.stdin.closed
                                            ):
                                                self.agent_process.stdin.write(b"yes\n")
                                                self.agent_process.stdin.flush()
                                        except Exception as confirm_err:
                                            logging.error(
                                                f"[bt-tether] Failed to auto-confirm: {confirm_err}"
                                            )

                                passkey_found_event.set()
                            elif "request confirmation" in clean_line.lower():
                                self._log("INFO", f"📱 {clean_line}")
                            elif clean_line.endswith("#"):
                                # Only log prompt changes to reduce spam
                                if clean_line != last_prompt:
                                    last_prompt = clean_line
                                    logging.debug(f"[bt-tether] Prompt: {clean_line}")
                            elif not clean_line.startswith("[CHG]"):
                                # Log other important output at debug level
                                logging.debug(f"[bt-tether] Agent: {clean_line}")
                    else:
                        # No new data, sleep briefly
                        time.sleep(self.DBUS_OPERATION_RETRY_DELAY)

            self._log(
                "INFO",
                f"Agent log monitoring timeout ({self.AGENT_LOG_MONITOR_TIMEOUT}s)",
            )
        except Exception as e:
            self._log("ERROR", f"Error monitoring agent log: {e}")

    def on_webhook(self, path, request):
        try:
            # Normalize path by stripping leading slash
            clean_path = path.lstrip("/") if path else ""

            if not clean_path:
                with self.lock:
                    return render_template_string(
                        HTML_TEMPLATE,
                        mac=self.phone_mac,
                        status=self.status,
                        message=self.message,
                        version=self.__version__,
                    )

            if clean_path == "trusted-devices":
                devices = self._get_trusted_devices()
                return jsonify({"devices": devices})

            if clean_path == "connect":
                mac = request.args.get("mac", "").strip().upper()

                # If MAC provided, use it; otherwise find best device automatically
                if mac and self._validate_mac(mac):
                    with self.lock:
                        self.phone_mac = mac
                        self.options["mac"] = self.phone_mac
                    self.start_connection()
                    # Force immediate screen update to show connecting state
                    if self._ui_reference:
                        try:
                            self.on_ui_update(self._ui_reference)
                        except Exception as e:
                            logging.debug(
                                f"[bt-tether] Error forcing UI update on connect: {e}"
                            )
                    return jsonify(
                        {"success": True, "message": f"Connection started to {mac}"}
                    )
                else:
                    # No MAC or invalid MAC - use smart device selection
                    best_device = self._find_best_device_to_connect()
                    if best_device:
                        with self.lock:
                            self.phone_mac = best_device["mac"]
                            self.options["mac"] = self.phone_mac
                        self.start_connection()
                        # Force immediate screen update to show connecting state
                        if self._ui_reference:
                            try:
                                self.on_ui_update(self._ui_reference)
                            except Exception as e:
                                logging.debug(
                                    f"[bt-tether] Error forcing UI update on connect: {e}"
                                )
                        return jsonify(
                            {
                                "success": True,
                                "message": f"Connection started to {best_device['name']} ({best_device['mac']})",
                            }
                        )
                    else:
                        return jsonify(
                            {
                                "success": False,
                                "message": "No suitable devices found - pair a device first or set MAC address",
                            }
                        )

            if clean_path == "pair-device":
                mac = request.args.get("mac", "").strip().upper()
                if mac and self._validate_mac(mac):
                    with self.lock:
                        self.phone_mac = mac
                        self.options["mac"] = self.phone_mac

                        # Check if connection is already in progress
                        if self._connection_in_progress:
                            return jsonify(
                                {
                                    "success": False,
                                    "message": "Connection already in progress",
                                }
                            )

                        # Stop any ongoing background scan and set connection in progress
                        self._stop_scan = True
                        self._scanning = False
                        self._connection_in_progress = True
                        self._connection_start_time = time.time()
                        self._user_requested_disconnect = False
                        self._screen_needs_refresh = True

                    # Reset failure counter
                    self._reconnect_failure_count = 0

                    # Unpause monitor
                    self._monitor_paused.clear()

                    # Create device info for unpaired device (will be paired during connection)
                    device_info = {
                        "mac": mac,
                        "name": request.args.get("name", "Unknown Device"),
                        "paired": False,
                        "trusted": False,
                        "connected": False,
                        "has_nap": True,  # Assume it has NAP, will be verified during connection
                    }

                    # Start connection thread directly with device info
                    threading.Thread(
                        target=self._connect_thread, args=(device_info,), daemon=True
                    ).start()

                    # Force immediate screen update to show pairing state
                    if self._ui_reference:
                        self.on_ui_update(self._ui_reference)

                    return jsonify(
                        {"success": True, "message": f"Pairing started with {mac}"}
                    )
                else:
                    return jsonify({"success": False, "message": "Invalid MAC address"})

            if clean_path == "status":
                with self.lock:
                    return jsonify(
                        {
                            "status": self.status,
                            "message": self.message,
                            "mac": self.phone_mac,
                            "disconnecting": self._disconnecting,
                            "untrusting": self._untrusting,
                            "initializing": self._initializing,
                            "connection_in_progress": self._connection_in_progress,
                        }
                    )

            if clean_path == "disconnect":
                mac = request.args.get("mac", "").strip().upper()
                if mac and self._validate_mac(mac):
                    # Set flags immediately so UI shows disconnecting state
                    with self.lock:
                        self._user_requested_disconnect = True
                        self._disconnecting = True
                        self._disconnect_start_time = (
                            time.time()
                        )  # Track when disconnect started
                        self._screen_needs_refresh = True

                    # Run disconnect in background thread so UI can update
                    def do_disconnect():
                        try:
                            # Return value intentionally ignored - state is communicated via flags
                            self._disconnect_device(mac)
                        except Exception as e:
                            logging.error(
                                f"[bt-tether] Background disconnect error: {e}"
                            )
                            # Ensure flags are cleared even on error
                            with self.lock:
                                self._disconnecting = False
                                self._connection_in_progress = False

                    thread = threading.Thread(target=do_disconnect, daemon=True)
                    thread.start()

                    # Force immediate screen update by calling on_ui_update if UI reference available
                    if self._ui_reference:
                        try:
                            self.on_ui_update(self._ui_reference)
                        except Exception as e:
                            logging.debug(
                                f"[bt-tether] Error forcing UI update on disconnect: {e}"
                            )

                    # Return immediately so pwnagotchi UI can refresh
                    return jsonify({"success": True, "message": "Disconnect started"})
                else:
                    return jsonify({"success": False, "message": "Invalid MAC"})

            if clean_path == "unpair":
                mac = request.args.get("mac", "").strip().upper()
                if mac and self._validate_mac(mac):
                    result = self._unpair_device(mac)
                    return jsonify(result)
                else:
                    return jsonify({"success": False, "message": "Invalid MAC"})

            if clean_path == "pair-status":
                mac = request.args.get("mac", "").strip().upper()
                if mac and self._validate_mac(mac):
                    status = self._check_pair_status(mac)
                    return jsonify(status)
                else:
                    return jsonify({"paired": False, "connected": False})

            if clean_path == "scan":
                with self.lock:
                    # If already scanning, return current real-time results
                    if self._scanning:
                        devices_to_return = list(self._discovered_devices.values())
                        return jsonify({"devices": devices_to_return, "scanning": True})

                    # Clear state for a fresh scan
                    self._last_scan_devices = []
                    self._discovered_devices = {}
                    self._scan_complete_time = 0
                    self._scanning = True
                    self._screen_needs_refresh = True

                # Run scan in background thread
                def run_scan_bg():
                    try:
                        devices = self._scan_devices()
                        with self.lock:
                            self._last_scan_devices = devices
                            # Rebuild _discovered_devices from final list
                            self._discovered_devices = {
                                device["mac"]: device for device in devices
                            }
                            self._scan_complete_time = time.time()
                            self._scanning = False  # Mark scan as complete
                        logging.info(
                            f"[bt-tether] Scan complete, found {len(devices)} devices"
                        )
                    except Exception as e:
                        logging.error(f"[bt-tether] Background scan error: {e}")
                        with self.lock:
                            self._scanning = False  # Clear flag even on error

                thread = threading.Thread(target=run_scan_bg, daemon=True)
                thread.start()

                if self._ui_reference:
                    try:
                        self.on_ui_update(self._ui_reference)
                    except Exception as e:
                        logging.debug(f"[bt-tether] Error forcing UI update: {e}")

                return jsonify({"devices": [], "scanning": True})

            if clean_path == "scan-progress":
                with self.lock:
                    devices = list(self._discovered_devices.values())
                    scanning = self._scanning
                return jsonify(
                    {"scanning": scanning, "devices": devices, "count": len(devices)}
                )

            if clean_path == "connection-status":
                mac = request.args.get("mac", "").strip().upper()
                if mac and self._validate_mac(mac):
                    status = self._get_full_connection_status(mac)
                    return jsonify(status)
                else:
                    return jsonify(
                        {
                            "paired": False,
                            "trusted": False,
                            "connected": False,
                            "pan_active": False,
                            "interface": None,
                            "ip_address": None,
                            "default_route_interface": None,
                        }
                    )

            if clean_path == "test-internet":
                result = self._test_internet_connectivity()
                return jsonify(result)

            if clean_path == "logs":
                with self._ui_log_lock:
                    logs = list(self._ui_logs)
                return jsonify({"logs": logs})

            return "Not Found", 404
        except Exception as e:
            logging.error(f"[bt-tether] Webhook error: {e}")
            return "Error", 500

    def _validate_mac(self, mac):
        """Validate MAC address format"""

        return bool(re.match(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", mac))

    def _disconnect_device(self, mac):
        """Disconnect from a Bluetooth device and remove trust to prevent auto-reconnect"""
        try:
            # Set flags to stop auto-reconnect and indicate disconnecting state
            with self.lock:
                self._user_requested_disconnect = True
                # Don't set _connection_in_progress during disconnect - causes "Connecting" to show
                self._disconnecting = True  # Set disconnecting flag for UI
                self._disconnect_start_time = time.time()  # Track disconnect start time
                self._initializing = False  # Clear initializing flag
                self.status = self.STATE_DISCONNECTING  # Set status for consistency
                self.message = f"Disconnecting from device..."
                self._screen_needs_refresh = (
                    True  # Force screen update to show disconnecting
                )

            # Update cached UI to show disconnecting state immediately
            self._update_cached_ui_status(
                status={
                    "paired": True,
                    "trusted": True,
                    "connected": False,
                    "pan_active": False,
                    "interface": None,
                    "ip_address": None,
                },
                mac=mac,
            )

            # Wait briefly for any ongoing reconnect to complete
            time.sleep(self.OPERATION_SHORT_DELAY)

            self._log("INFO", f"Disconnecting from device {mac}...")

            # FIRST: Disconnect NAP profile via DBus if connected
            try:
                import dbus

                bus = dbus.SystemBus()
                manager = dbus.Interface(
                    bus.get_object("org.bluez", "/"),
                    "org.freedesktop.DBus.ObjectManager",
                )
                objects = manager.GetManagedObjects()
                device_path = None
                for path, interfaces in objects.items():
                    if "org.bluez.Device1" in interfaces:
                        props = interfaces["org.bluez.Device1"]
                        if props.get("Address") == mac:
                            device_path = path
                            break

                if device_path:
                    device = dbus.Interface(
                        bus.get_object("org.bluez", device_path), "org.bluez.Device1"
                    )
                    try:
                        self._log("INFO", "Disconnecting NAP profile...")
                        device.DisconnectProfile(self.NAP_UUID)
                        time.sleep(self.DEVICE_OPERATION_DELAY)
                        self._log("INFO", "NAP profile disconnected")
                    except Exception as e:
                        logging.debug(f"[bt-tether] NAP disconnect: {e}")
            except Exception as e:
                logging.debug(f"[bt-tether] DBus operation: {e}")

            # Disconnect the Bluetooth connection
            self._log("INFO", "Disconnecting Bluetooth...")
            result = self._run_cmd(["bluetoothctl", "disconnect", mac], capture=True)
            self._log("INFO", f"Disconnect result: {result}")
            time.sleep(self.DEVICE_OPERATION_LONGER_DELAY)

            # Remove trust to prevent automatic reconnection
            self._log("INFO", "Removing trust to prevent auto-reconnect...")
            # Keep showing "Disconnecting" state throughout the entire cleanup process
            # No need to switch to "Untrusting" state - it's all part of disconnect

            # Update cached UI to show untrusting state
            self._update_cached_ui_status(
                status={
                    "paired": True,
                    "trusted": False,
                    "connected": False,
                    "pan_active": False,
                    "interface": None,
                    "ip_address": None,
                },
                mac=mac,
            )

            trust_result = self._run_cmd(["bluetoothctl", "untrust", mac], capture=True)
            self._log("INFO", f"Untrust result: {trust_result}")
            time.sleep(self.DEVICE_OPERATION_DELAY)

            # Update cached UI status after untrust but before clearing flag
            self._update_cached_ui_status(
                status={
                    "paired": True,
                    "trusted": False,
                    "connected": False,
                    "pan_active": False,
                    "interface": None,
                    "ip_address": None,
                },
                mac=mac,
            )

            with self.lock:
                # Keep disconnecting state throughout - don't switch states
                self._disconnect_start_time = time.time()
                self.message = f"Finalizing disconnect..."
                self._screen_needs_refresh = True

            # Block the device BEFORE removing it to prevent reconnection attempts
            self._log("INFO", "Blocking device to prevent reconnection...")
            block_result = self._run_cmd(["bluetoothctl", "block", mac], capture=True)
            self._log("INFO", f"Block result: {block_result}")
            time.sleep(self.DEVICE_OPERATION_DELAY)

            # Unpair (remove) the device completely
            self._log("INFO", "Removing device to unpair...")
            remove_result = self._run_cmd(["bluetoothctl", "remove", mac], capture=True)
            self._log("INFO", f"Remove result: {remove_result}")
            time.sleep(
                self.DEVICE_OPERATION_LONGER_DELAY
            )  # Wait longer for changes to propagate

            self._log(
                "INFO", f"Device {mac} disconnected, blocked and removed successfully"
            )

            # Emit disconnection event for manual user disconnect
            event_data = {
                "mac": mac,
                "device": self.phone_mac or "unknown",
                "reason": "user_request",
            }
            self._emit_event("bt_tether_disconnected", event_data)

            # Update cached UI status to disconnected state FIRST
            self._update_cached_ui_status(
                status={
                    "paired": False,
                    "trusted": False,
                    "connected": False,
                    "pan_active": False,
                    "interface": None,
                    "ip_address": None,
                }
            )

            # Then update internal state
            with self.lock:
                self.status = self.STATE_DISCONNECTED
                self.message = "No device"  # Show "No device" when fully disconnected
                self._disconnecting = False  # Clear disconnecting flag
                self._disconnect_start_time = None
                self._last_known_connected = False
                # Clear phone_mac so monitor doesn't try to reconnect
                self.phone_mac = ""
                # Clear passkey after disconnect
                self.current_passkey = None
                self._screen_needs_refresh = True

            # Force immediate screen update to show fully disconnected state
            if self._ui_reference:
                try:
                    self.on_ui_update(self._ui_reference)
                except Exception as e:
                    logging.debug(
                        f"[bt-tether] Error forcing UI update on disconnected: {e}"
                    )

            # Return success
            return {
                "success": True,
                "message": f"Device {mac} disconnected, unpaired, and blocked",
            }
        except Exception as e:
            self._log("ERROR", f"Disconnect error: {e}")
            # Update cached UI status to show error FIRST
            self._update_cached_ui_status()

            self._set_state(
                self.STATE_ERROR,
                f"Disconnect failed: {str(e)[:50]}",
                _initializing=False,
            )
            return {"success": False, "message": f"Disconnect failed: {str(e)}"}
        finally:
            # Always clear the flags, even if disconnect fails
            with self.lock:
                self._disconnecting = False
                self._disconnect_start_time = None
                self._untrusting = False
                self._untrust_start_time = None

    def _unpair_device(self, mac):
        """Unpair a Bluetooth device"""
        try:
            self._log("INFO", f"Unpairing device {mac}...")
            result = self._run_cmd(
                ["bluetoothctl", "remove", mac],
                capture=True,
                timeout=self.SUBPROCESS_TIMEOUT_LONG,
            )

            if result == "Timeout":
                self._log("WARNING", "Unpair command timed out")
                # Still consider it successful - device is likely already gone
                return {
                    "success": True,
                    "message": "Device was already unpaired or removed",
                }
            elif result and "Device has been removed" in result:
                self._log("INFO", f"Device {mac} unpaired successfully")

                # Update internal state
                with self.lock:
                    self.status = self.STATE_DISCONNECTED
                    self.message = "Device unpaired"
                    self._last_known_connected = False
                    # Clear passkey after unpair
                    self.current_passkey = None
                    self._screen_needs_refresh = True

                # Update cached UI status
                self._update_cached_ui_status()

                return {
                    "success": True,
                    "message": f"Device {mac} unpaired successfully",
                }
            elif result and (
                "not available" in result or "not found" in result.lower()
            ):
                self._log("INFO", f"Device {mac} was already removed")
                return {
                    "success": True,
                    "message": f"Device {mac} was already unpaired",
                }
            else:
                self._log("WARNING", f"Unpair result: {result}")
                return {"success": True, "message": f"Unpair command sent: {result}"}
        except Exception as e:
            self._log("ERROR", f"Unpair error: {e}")
            return {"success": False, "message": f"Unpair failed: {str(e)}"}

    def _check_pair_status(self, mac):
        """Check if a device is already paired"""
        try:
            info = self._run_cmd(["bluetoothctl", "info", mac], capture=True)
            if not info or "Device" not in info:
                return {"paired": False, "connected": False, "known_to_bluez": False}

            paired = "Paired: yes" in info
            connected = "Connected: yes" in info

            logging.debug(
                f"[bt-tether] Device {mac} - Paired: {paired}, Connected: {connected}"
            )
            return {"paired": paired, "connected": connected, "known_to_bluez": True}
        except Exception as e:
            self._log("ERROR", f"Pair status check error: {e}")
            return {"paired": False, "connected": False, "known_to_bluez": False}

    def _get_current_status(self, mac):
        """Get current connection status - no cache, direct check"""
        try:
            # Quick check: look for active PAN interface first (fastest indicator)
            # Check for both bnep and bt-pan interfaces
            try:
                pan_result = subprocess.run(
                    ["ip", "link", "show"],
                    capture_output=True,
                    text=True,
                    timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
                )
                if pan_result.returncode == 0:
                    # Find the PAN interface name (bnep0, bnep1, bt-pan, etc.)
                    pan_iface = None
                    for link_line in pan_result.stdout.split("\n"):
                        for prefix in ("bnep", "bt-pan"):
                            if prefix in link_line:
                                # Extract interface name from lines like "5: bnep0: <...>"
                                match = re.search(r"\d+:\s+(\S+?)[@:]", link_line)
                                if match:
                                    pan_iface = match.group(1)
                                    break
                        if pan_iface:
                            break

                    if pan_iface:
                        # Check if PAN interface has an IP address
                        try:
                            ip_result = subprocess.run(
                                ["ip", "addr", "show", pan_iface],
                                capture_output=True,
                                text=True,
                                timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
                            )
                            if (
                                ip_result.returncode == 0
                                and "inet " in ip_result.stdout
                            ):
                                # Extract IP address from the output
                                ip_address = None
                                for line in ip_result.stdout.split("\n"):
                                    if "inet " in line and not "127.0.0.1" in line:
                                        parts = line.strip().split()
                                        for part in parts:
                                            if part.startswith("inet"):
                                                continue
                                            if "/" in part and "." in part:
                                                ip_address = part.split("/")[0]
                                                break
                                        if ip_address:
                                            break

                                # PAN interface exists and has IP, we're connected with internet
                                return {
                                    "paired": True,
                                    "trusted": True,
                                    "connected": True,
                                    "pan_active": True,
                                    "interface": pan_iface,
                                    "ip_address": ip_address,
                                }
                        except Exception as ip_err:
                            logging.debug(f"[bt-tether] IP check failed: {ip_err}")
            except Exception as pan_err:
                logging.debug(f"[bt-tether] PAN check failed: {pan_err}")

            # Quick bluetoothctl check with minimal timeout
            try:
                result = subprocess.run(
                    ["bluetoothctl", "info", mac],
                    capture_output=True,
                    text=True,
                    timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
                )

                if result.returncode == 0 and result.stdout:
                    info = result.stdout
                    paired = "Paired: yes" in info
                    connected = "Connected: yes" in info
                    trusted = "Trusted: yes" in info

                    return {
                        "paired": paired,
                        "trusted": trusted,
                        "connected": connected,
                        "pan_active": False,  # Already checked above
                        "interface": None,
                        "ip_address": None,
                    }
            except Exception as bt_err:
                logging.debug(f"[bt-tether] bluetoothctl check failed: {bt_err}")

            # Fallback to disconnected if all checks fail
            return {
                "paired": False,
                "trusted": False,
                "connected": False,
                "pan_active": False,
                "interface": None,
                "ip_address": None,
            }

        except Exception as e:
            logging.debug(f"[bt-tether] Status check error: {e}")
            return {
                "paired": False,
                "trusted": False,
                "connected": False,
                "pan_active": False,
                "interface": None,
                "ip_address": None,
            }

    def _get_full_connection_status(self, mac):
        """Get complete connection status for web UI - includes additional fields"""
        # Get base status
        status = self._get_current_status(mac)

        # Add default_route_interface for web UI display
        try:
            status["default_route_interface"] = self._get_default_route_interface()
        except Exception as e:
            logging.debug(f"[bt-tether] Failed to get default route interface: {e}")
            status["default_route_interface"] = None

        return status

    def _get_trusted_devices(self):
        """Get list of all trusted Bluetooth devices with their info"""
        try:
            trusted_devices = []

            # Get list of all paired devices
            devices_output = self._run_cmd(
                ["bluetoothctl", "devices", "Paired"],
                capture=True,
                timeout=self.SUBPROCESS_TIMEOUT_LONG,
            )

            if not devices_output or devices_output == "Timeout":
                return trusted_devices

            # Check each device for trust status and get detailed info
            for line in devices_output.split("\n"):
                if line.strip() and line.startswith("Device"):
                    parts = line.strip().split(" ", 2)
                    if len(parts) >= 2:
                        mac = parts[1]
                        name = parts[2] if len(parts) > 2 else "Unknown Device"

                        # Get device info to check trust status and capabilities
                        info = self._run_cmd(
                            ["bluetoothctl", "info", mac],
                            capture=True,
                            timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                        )
                        if info and "Trusted: yes" in info:
                            # Parse additional device info
                            device_info = {
                                "mac": mac,
                                "name": name,
                                "trusted": True,
                                "paired": "Paired: yes" in info,
                                "connected": "Connected: yes" in info,
                                "has_nap": self.NAP_UUID in info,  # NAP UUID
                            }
                            trusted_devices.append(device_info)

            return trusted_devices

        except Exception as e:
            self._log("ERROR", f"Failed to get trusted devices: {e}")
            return []

    def _find_best_device_to_connect(self, log_results=True):
        """Find the best device to connect to (trusted devices first, then configured MAC)

        Args:
            log_results: Whether to log the results (default True, set False to reduce spam)
        """
        try:
            # First check for trusted devices with NAP capability
            trusted_devices = self._get_trusted_devices()

            # Filter for devices that support NAP (tethering)
            nap_devices = [d for d in trusted_devices if d["has_nap"]]

            if nap_devices:
                if log_results:
                    self._log(
                        "INFO",
                        f"Found {len(nap_devices)} trusted device(s) with tethering capability",
                    )

                # Prioritization logic:
                # 1. Currently connected devices first
                # 2. Devices that match configured MAC (if any)
                # 3. First available device

                connected_devices = [d for d in nap_devices if d["connected"]]
                if connected_devices:
                    device = connected_devices[0]
                    if log_results:
                        self._log(
                            "INFO",
                            f"Using already connected device: {device['name']} ({device['mac']})",
                        )
                    return device

                # If we have a configured MAC, prefer it if it's in the trusted list
                if self.phone_mac:
                    for device in nap_devices:
                        if device["mac"].upper() == self.phone_mac.upper():
                            self._log(
                                "INFO",
                                f"Using configured trusted device: {device['name']} ({device['mac']})",
                            )
                            return device

                # Return first available NAP device
                device = nap_devices[0]
                self._log(
                    "INFO",
                    f"Auto-selected NAP device: {device['name']} ({device['mac']})",
                )
                return device

            # No devices found
            # Only warn if explicitly requested to log results
            if log_results:
                self._log(
                    "WARNING",
                    "No trusted devices with tethering capability found",
                )
            return None

        except Exception as e:
            self._log("ERROR", f"Failed to find best device: {e}")
            return None

    def _scan_devices(self):
        """Scan for Bluetooth devices using interactive bluetoothctl session"""
        try:
            logging.info("[bt-tether] Starting device scan...")
            # Reset stop flag at start of new scan
            self._stop_scan = False
            self._log("INFO", "Starting scan...")
            self._log("INFO", f"Scanning for {self.SCAN_DURATION} seconds...")
            discovered_devices = {}
            device_types = {}  # Track whether each device is NEW or already PAIRED

            # Pre-populate with cached paired devices so they appear immediately in the UI
            self._log("DEBUG", "Loading existing paired devices...")
            try:
                paired_output = self._run_cmd(
                    ["bluetoothctl", "devices", "Paired"],
                    capture=True,
                    timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                )
                if paired_output and paired_output != "Timeout":
                    for line in paired_output.split("\n"):
                        if line.strip() and line.startswith("Device"):
                            parts = line.strip().split(" ", 2)
                            if len(parts) >= 3:
                                mac = parts[1].upper()
                                name = parts[2]
                                if mac not in discovered_devices:
                                    discovered_devices[mac] = name
                                    device_types[mac] = "PAIRED"
                                    self._log(
                                        "DEBUG",
                                        f"Pre-loaded cached device: {name} ({mac})",
                                    )
            except Exception as e:
                logging.debug(f"[bt-tether] Error pre-loading paired devices: {e}")

            # Update _discovered_devices with cached devices so /scan-progress shows
            # paired devices immediately while the active scan runs
            with self.lock:
                self._discovered_devices = {
                    mac: {
                        "mac": mac,
                        "name": discovered_devices[mac],
                        "type": device_types.get(mac, "UNKNOWN"),
                    }
                    for mac in discovered_devices
                }

            lines_read = 0
            try:
                # Ensure Bluetooth is powered on
                self._log("DEBUG", "Ensuring Bluetooth is powered on...")
                self._run_cmd(
                    ["bluetoothctl", "power", "on"],
                    timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                )
                time.sleep(self.OPERATION_SHORT_DELAY)

                mac_pattern = self.SCAN_MAC_PATTERN
                ansi_pattern = self.SCAN_ANSI_PATTERN
                self._log("DEBUG", "Starting bluetoothctl in interactive mode...")
                scan_start = time.time()
                scan_process = None
                try:
                    env = dict(os.environ)
                    env["TERM"] = "dumb"
                    scan_process = subprocess.Popen(
                        ["bluetoothctl"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,  # Line buffered
                        env=env,
                    )
                    # Send scan on command to start scanning
                    scan_process.stdin.write("scan on\n")
                    scan_process.stdin.flush()
                except Exception as e:
                    self._log("ERROR", f"Failed to start scan: {e}")
                    scan_process = None

                if scan_process:
                    self._log("DEBUG", f"Scanning for {self.SCAN_DURATION} seconds...")
                    self._log("DEBUG", f"Process started, PID: {scan_process.pid}")
                    scan_end_time = time.time() + self.SCAN_DURATION
                    try:
                        while time.time() < scan_end_time and not self._stop_scan:
                            try:
                                import select

                                ready = select.select(
                                    [scan_process.stdout], [], [], 0.5
                                )
                                if ready[0]:
                                    line = scan_process.stdout.readline()
                                    if not line:
                                        break
                                    line = line.strip()
                                    if not line:
                                        continue
                                    lines_read += 1
                                    # Strip ANSI codes for pattern matching
                                    clean_line = ansi_pattern.sub("", line)
                                    # Parse discovery events: "[NEW] Device MAC Name"
                                    if "[NEW]" in clean_line and "Device" in clean_line:
                                        mac_match = mac_pattern.search(clean_line)
                                        if mac_match:
                                            mac = mac_match.group(1).upper()
                                            remainder = clean_line[
                                                mac_match.end() :
                                            ].strip()
                                            name = (
                                                remainder if remainder else "(unnamed)"
                                            )
                                            if mac not in discovered_devices:
                                                discovered_devices[mac] = name
                                                device_types[mac] = "NEW"
                                                self._log(
                                                    "INFO",
                                                    f"[NEW] {name} ({mac})",
                                                )
                                                # Update real-time list for /scan-progress
                                                with self.lock:
                                                    self._discovered_devices[mac] = {
                                                        "mac": mac,
                                                        "name": name,
                                                        "type": device_types[mac],
                                                    }
                            except select.error:
                                pass
                    finally:
                        # Stop scan and close bluetoothctl
                        self._log("DEBUG", "Stopping scan...")
                        try:
                            try:
                                self._run_cmd(
                                    ["bluetoothctl", "scan", "off"],
                                    timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
                                )
                            except Exception:
                                pass
                            time.sleep(self.SCAN_STOP_DELAY)
                            scan_process.stdin.write("quit\n")
                            scan_process.stdin.flush()
                            try:
                                scan_process.wait(
                                    timeout=self.SUBPROCESS_TIMEOUT_MEDIUM
                                )
                                logging.info(
                                    "[bt-tether] Bluetoothctl process exited cleanly"
                                )
                            except subprocess.TimeoutExpired:
                                logging.info(
                                    "[bt-tether] Force killing bluetoothctl after timeout"
                                )
                                scan_process.kill()
                                scan_process.wait(timeout=self.SUBPROCESS_TIMEOUT_SHORT)
                        except Exception as e:
                            logging.debug(f"[bt-tether] Error stopping scan: {e}")
                            try:
                                scan_process.kill()
                            except Exception:
                                pass

                    elapsed = time.time() - scan_start
                    self._log(
                        "INFO",
                        f"Scan completed in {elapsed:.1f}s, found {len(discovered_devices)} device(s)",
                    )
            except Exception as e:
                self._log("ERROR", f"Error during scan: {e}")
                logging.exception("[bt-tether] Scan exception:")

            # Pick up any devices that were paired during the scan itself
            self._log("DEBUG", "Checking for any newly paired devices...")
            try:
                paired_output = self._run_cmd(
                    ["bluetoothctl", "devices", "Paired"],
                    capture=True,
                    timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                )
                if paired_output and paired_output != "Timeout":
                    for line in paired_output.split("\n"):
                        if line.strip() and line.startswith("Device"):
                            parts = line.strip().split(" ", 2)
                            if len(parts) >= 3:
                                mac = parts[1].upper()
                                name = parts[2]
                                if mac not in discovered_devices:
                                    discovered_devices[mac] = name
                                    device_types[mac] = "PAIRED"
                                    with self.lock:
                                        self._discovered_devices[mac] = {
                                            "mac": mac,
                                            "name": name,
                                            "type": "PAIRED",
                                        }
                                    self._log(
                                        "INFO",
                                        f"Found device paired during scan: {name} ({mac})",
                                    )
            except Exception as e:
                logging.debug(
                    f"[bt-tether] Error checking for newly paired devices: {e}"
                )

            # Convert to list format
            devices = [
                {
                    "mac": mac,
                    "name": discovered_devices[mac],
                    "type": device_types.get(mac, "UNKNOWN"),
                }
                for mac in discovered_devices
            ]
            logging.info(f"[bt-tether] Scan complete. Found {len(devices)} devices")
            if devices:
                self._log("INFO", f"=== Discovered {len(devices)} device(s) ===")
                for i, device in enumerate(devices, 1):
                    self._log("INFO", f"  [{i}] {device['name']} ({device['mac']})")
            else:
                self._log("WARNING", "No devices found during scan")
                self._log("WARNING", "Ensure phone Bluetooth is ON and discoverable")
            return devices

        except Exception as e:
            self._log("ERROR", f"Scan error: {e}")
            logging.exception("[bt-tether] Scan exception:")
            return []

    def start_connection(self):
        with self.lock:
            # Find the best device to connect to (trusted devices or configured MAC)
            best_device = self._find_best_device_to_connect()

            if not best_device:
                self.status = self.STATE_ERROR
                self.message = "No trusted devices found - scan and pair a device first"
                self._screen_needs_refresh = True
                return

            # Update current target MAC
            self.phone_mac = best_device["mac"]
            self.options["mac"] = self.phone_mac

            # Check if connection is already in progress (prevents multiple threads)
            if self._connection_in_progress:
                self._log(
                    "WARNING",
                    "Connection already in progress, ignoring duplicate request",
                )
                self.message = "Connection already in progress"
                self._screen_needs_refresh = True
                return

            if self.status in [self.STATE_PAIRING, self.STATE_CONNECTING]:
                self._log(
                    "WARNING", "Already pairing/connecting, ignoring duplicate request"
                )
                self.message = "Connection already in progress"
                self._screen_needs_refresh = True
                return

            # Set flag INSIDE the lock to prevent race condition
            self._connection_in_progress = True
            self._connection_start_time = time.time()  # Track when connection started
            self._user_requested_disconnect = False  # Re-enable auto-reconnect
            self.status = self.STATE_CONNECTING
            self.message = f"Connecting to {best_device['name']}..."
            self.phone_mac = best_device[
                "mac"
            ]  # Set phone_mac immediately so screen knows which device we're connecting to

        # Update cached UI status immediately so screen shows connecting state
        # Use current status - device may be paired/trusted from before
        self._update_cached_ui_status(mac=best_device["mac"])

        # Reset failure counter on manual reconnect
        self._reconnect_failure_count = 0

        # Unpause monitor since we have a device to monitor
        self._monitor_paused.clear()

        # Pass device info to connection thread
        threading.Thread(
            target=self._connect_thread, args=(best_device,), daemon=True
        ).start()

    def _connect_thread(self, target_device):
        """Full automatic connection thread with pairing and connection logic"""
        try:
            mac = target_device["mac"]
            device_name = target_device["name"]
            self._log("INFO", f"Starting connection to {device_name} ({mac})...")

            # Check if Bluetooth is responsive, restart if needed
            if not self._restart_bluetooth_if_needed():
                self._log(
                    "ERROR",
                    "Bluetooth service is unresponsive and couldn't be restarted",
                )
                with self.lock:
                    self.status = self.STATE_ERROR
                    self.message = "Bluetooth service unresponsive. Try: sudo systemctl restart bluetooth"
                    self._connection_in_progress = False
                return

            # Make Pwnagotchi discoverable and pairable
            self._log("INFO", f"Making Pwnagotchi discoverable...")
            with self.lock:
                self.message = f"Making Pwnagotchi discoverable for {device_name}..."
                self._screen_needs_refresh = True
            self._run_cmd(["bluetoothctl", "discoverable", "on"], capture=True)
            self._run_cmd(["bluetoothctl", "pairable", "on"], capture=True)
            time.sleep(self.DEVICE_OPERATION_LONGER_DELAY)

            # First check current pairing status
            with self.lock:
                self.message = f"Checking pairing status with {device_name}..."
                self._screen_needs_refresh = True
            pair_status = self._check_pair_status(mac)

            # If device is not trusted/paired, we need to pair first
            if not pair_status["paired"]:
                known_to_bluez = pair_status.get("known_to_bluez", False)

                if known_to_bluez:
                    # BlueZ has a stale/broken bond — remove it for a clean pair
                    self._log(
                        "INFO",
                        "Device not paired but known to BlueZ. Removing stale bond...",
                    )
                    with self.lock:
                        self.message = f"Clearing stale pairing with {device_name}..."
                        self._screen_needs_refresh = True
                    self._run_cmd(["bluetoothctl", "remove", mac], capture=True)
                    time.sleep(self.DEVICE_OPERATION_DELAY)
                    needs_discovery = True  # remove wiped BlueZ cache, must rediscover
                else:
                    # Truly new device — BlueZ already knows it from the background scan
                    self._log(
                        "INFO", "Device not yet paired. Starting fresh pairing..."
                    )
                    needs_discovery = False  # BlueZ still has it from scan

                self._log("INFO", f"Unblocking {device_name} in case it was blocked...")
                with self.lock:
                    self.message = f"Unblocking {device_name}..."
                    self._screen_needs_refresh = True
                self._run_cmd(["bluetoothctl", "unblock", mac], capture=True)
                time.sleep(self.DEVICE_OPERATION_DELAY)

                # Start pairing process - set PAIRING state
                self._log(
                    "INFO",
                    f"Device not paired. Starting pairing process with {device_name}...",
                )
                with self.lock:
                    self.status = self.STATE_PAIRING
                    self.message = f"Pairing with {device_name}..."
                    self._screen_needs_refresh = True

                # Brief delay to ensure PAIRING state is displayed
                time.sleep(self.OPERATION_SHORT_DELAY)

                # Attempt pairing - this will show dialog on phone
                if not self._pair_device_interactive(
                    mac, needs_discovery=needs_discovery
                ):
                    self._log("ERROR", f"Pairing with {device_name} failed!")
                    with self.lock:
                        self.status = self.STATE_ERROR
                        self.message = f"Pairing with {device_name} failed. Did you accept the dialog?"
                        self._connection_in_progress = False
                        self._screen_needs_refresh = True
                    # Force immediate screen update to show error state
                    if self._ui_reference:
                        try:
                            self.on_ui_update(self._ui_reference)
                        except Exception as e:
                            logging.debug(
                                f"[bt-tether] Error forcing UI update on pairing error: {e}"
                            )
                    return

                self._log("INFO", f"Pairing with {device_name} successful!")
            else:
                self._log("INFO", f"Device {device_name} already paired")
                with self.lock:
                    self.message = f"Device {device_name} already paired ✓"
                    self._screen_needs_refresh = True

            # Trust the device - set TRUSTING state
            logging.info(f"[bt-tether] Trusting device {device_name}...")
            with self.lock:
                self.status = self.STATE_TRUSTING
                self.message = f"Trusting {device_name}..."
                self._screen_needs_refresh = True

            # Brief delay to ensure TRUSTING state is displayed
            time.sleep(self.OPERATION_SHORT_DELAY)

            self._run_cmd(["bluetoothctl", "trust", mac])

            # Wait until the phone's NAP service UUID appears in bluetoothctl info.
            # This is more reliable than a fixed sleep: the NAP UUID appearing means
            # the phone's tethering/NAP service is actually ready to accept connections.
            # br-connection-create-socket occurs when we connect before this is ready.
            NAP_UUID = "00001116"  # NAP profile UUID prefix
            NAP_WAIT_TIMEOUT = 15
            logging.info(
                f"[bt-tether] Waiting for {device_name} NAP service to be ready..."
            )
            with self.lock:
                self.message = f"Waiting for {device_name} to be ready..."
                self._screen_needs_refresh = True
            nap_ready = False
            nap_wait_start = time.time()
            while time.time() - nap_wait_start < NAP_WAIT_TIMEOUT:
                info = self._run_cmd(
                    ["bluetoothctl", "info", mac],
                    capture=True,
                    timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
                )
                if info and NAP_UUID in info:
                    elapsed = time.time() - nap_wait_start
                    logging.info(f"[bt-tether] NAP service ready after {elapsed:.1f}s")
                    nap_ready = True
                    break
                time.sleep(self.DEVICE_OPERATION_DELAY)
            if not nap_ready:
                logging.warning(
                    f"[bt-tether] NAP UUID not seen after {NAP_WAIT_TIMEOUT}s - proceeding anyway"
                )

            # Proceed directly to NAP connection (this establishes BT connection if needed)
            self._log("INFO", "Connecting to NAP profile...")
            with self.lock:
                self.status = self.STATE_CONNECTING
                self.message = "Connecting to NAP profile for internet..."
                self._screen_needs_refresh = True

            # Brief delay to ensure CONNECTING state is displayed
            time.sleep(self.OPERATION_SHORT_DELAY)

            # Try to establish PAN connection
            self._log("INFO", "Establishing PAN connection...")
            with self.lock:
                self.status = self.STATE_CONNECTING
                self.message = "Connecting to NAP profile for internet..."
                self._screen_needs_refresh = True

            # Try DBus connection to NAP profile (with retry for br-connection-busy)
            nap_connected = False
            for retry in range(3):
                if retry > 0:
                    self._log(
                        "info", f"Retrying NAP connection (attempt {retry + 1}/3)..."
                    )
                    with self.lock:
                        self.message = f"NAP retry {retry + 1}/3..."
                        self._screen_needs_refresh = True
                    time.sleep(
                        self.OPERATION_MEDIUM_DELAY
                    )  # Wait for previous connection attempt to settle

                nap_connected = self._connect_nap_dbus(mac)
                if nap_connected:
                    break
                else:
                    self._log("WARNING", f"NAP attempt {retry + 1} failed")
                    with self.lock:
                        self.message = f"NAP attempt {retry + 1}/3 failed..."
                        self._screen_needs_refresh = True

            if nap_connected:
                self._log("INFO", "NAP connection successful!")

                # Check if PAN interface is up
                if self._pan_active():
                    iface = self._get_pan_interface()
                    self._log("INFO", f"✓ PAN interface active: {iface}")

                    # Wait for interface initialization
                    self._log("INFO", "Waiting for interface initialization...")
                    time.sleep(2)

                    # Setup network with DHCP
                    if self._setup_network_dhcp(iface):
                        self._log("INFO", "✓ Network setup successful")

                        # Ensure DNS is configured from DHCP
                        self._log("INFO", "Verifying DNS configuration...")
                        try:
                            with open("/etc/resolv.conf", "r") as f:
                                resolv_content = f.read()
                                nameservers = [
                                    line.strip()
                                    for line in resolv_content.split("\n")
                                    if line.strip().startswith("nameserver")
                                ]
                                if nameservers:
                                    self._log(
                                        "INFO",
                                        f"✓ DNS configured: {', '.join([ns.split()[1] for ns in nameservers])}",
                                    )
                                else:
                                    self._log(
                                        "WARNING",
                                        "No nameservers found in /etc/resolv.conf - DNS may not work",
                                    )
                        except Exception as e:
                            self._log("WARNING", f"Could not verify DNS config: {e}")
                    else:
                        self._log(
                            "warning",
                            "Network setup failed, connection may not work",
                        )

                    # Wait a bit for network to stabilize
                    time.sleep(self.DEVICE_OPERATION_LONGER_DELAY)

                    # Verify internet connectivity
                    self._log("INFO", "Checking internet connectivity...")
                    with self.lock:
                        self.message = "Verifying internet connection..."
                        self._screen_needs_refresh = True

                    if self._check_internet_connectivity():
                        self._log("INFO", "✓ Internet connectivity verified!")

                        # Get current IP address for event data
                        try:
                            current_ip = self._get_current_ip()
                            if current_ip:
                                self._log("INFO", f"Current IP address: {current_ip}")

                                # Now test DNS resolution after we have confirmed IP
                                self._log("INFO", "Testing DNS resolution...")
                                try:
                                    import socket

                                    socket.gethostbyname("google.com")
                                    self._log("INFO", "✓ DNS resolution working")
                                except socket.gaierror:
                                    self._log(
                                        "WARNING",
                                        "DNS resolution failed - check /etc/resolv.conf",
                                    )
                                except Exception as dns_e:
                                    self._log("WARNING", f"DNS test error: {dns_e}")
                        except Exception as e:
                            self._log("ERROR", f"Failed to get IP or test DNS: {e}")

                        # Update cached UI status with fresh data FIRST
                        self._update_cached_ui_status(mac=mac)

                        # Emit connected event for plugins to listen to
                        self._emit_event(
                            "bt_tether_connected",
                            {
                                "mac": mac,
                                "device": device_name,
                                "ip": self._get_current_ip() or "unknown",
                                "interface": iface,
                            },
                        )

                        # Then set status and clear flags atomically
                        with self.lock:
                            self.status = self.STATE_CONNECTED
                            self.message = f"✓ Connected! Internet via {iface}"
                            self._connection_in_progress = False
                            self._connection_start_time = None
                            self._initializing = False
                            self._screen_needs_refresh = True

                        # Log for debugging
                        self._log("DEBUG", "Connection complete, flags cleared")

                        # Force immediate screen update to show IP/connected state
                        if self._ui_reference:
                            try:
                                self.on_ui_update(self._ui_reference)
                            except Exception as e:
                                logging.debug(
                                    f"[bt-tether] Error forcing UI update on success: {e}"
                                )

                    else:
                        self._log("WARNING", "No internet connectivity detected")
                        # Update cached UI status FIRST
                        self._update_cached_ui_status(mac=mac)

                        with self.lock:
                            self.status = self.STATE_CONNECTED
                            self.message = (
                                f"Connected via {iface} but no internet access"
                            )
                            self._connection_in_progress = False
                            self._connection_start_time = None
                            self._initializing = False
                            self._screen_needs_refresh = True

                        # Force immediate screen update
                        if self._ui_reference:
                            try:
                                self.on_ui_update(self._ui_reference)
                            except Exception as e:
                                logging.debug(
                                    f"[bt-tether] Error forcing UI update on no-internet: {e}"
                                )
                else:
                    self._log("WARNING", "NAP connected but no interface detected")
                    # Update cached UI status first
                    self._update_cached_ui_status(mac=mac)

                    with self.lock:
                        self.status = self.STATE_CONNECTED
                        self.message = "Connected but no internet. Enable Bluetooth tethering on phone."
                        self._connection_in_progress = False
                        self._connection_start_time = None
                        self._initializing = False
                        self._screen_needs_refresh = True
            else:
                self._log("WARNING", "NAP connection failed")

                # Update cached UI status FIRST
                self._update_cached_ui_status(mac=mac)

                # Then clear flags so on_ui_update doesn't show connecting
                with self.lock:
                    self.status = self.STATE_CONNECTED
                    self.message = "Bluetooth connected but tethering failed. Enable tethering on phone."
                    self._connection_in_progress = False  # Clear connection flag
                    self._connection_start_time = None
                    self._initializing = False  # Clear initializing flag
                    self._screen_needs_refresh = True
                # Force immediate screen update
                if self._ui_reference:
                    try:
                        self.on_ui_update(self._ui_reference)
                    except Exception as e:
                        logging.debug(
                            f"[bt-tether] Error forcing UI update on NAP failure: {e}"
                        )

        except Exception as e:
            self._log("ERROR", f"Connection thread error: {e}")
            self._log("ERROR", f"Traceback: {traceback.format_exc()}")
            # Update cached UI status to show error FIRST
            self._update_cached_ui_status()

            self._set_state(
                self.STATE_ERROR,
                f"Connection error: {str(e)}",
                _connection_in_progress=False,
                _connection_start_time=None,
            )
        finally:
            # Clear the flag if not already cleared (error cases)
            with self.lock:
                if self._connection_in_progress:
                    self._connection_in_progress = False
                    self._connection_start_time = None

            # Force immediate screen update to show final state (connected or error)
            if self._ui_reference:
                try:
                    self.on_ui_update(self._ui_reference)
                except Exception as e:
                    logging.debug(
                        f"[bt-tether] Error forcing UI update in finally: {e}"
                    )

    def _strip_ansi_codes(self, text):
        """Remove ANSI color/control codes from text"""
        if not text:
            return text

        # Remove ANSI escape sequences
        ansi_escape = re.compile(r"\x1b\[[0-9;]*[mGKHF]|\x01|\x02")
        text = ansi_escape.sub("", text)

        # Filter out bluetoothctl status lines ([CHG], [DEL], [NEW]) to prevent log parser errors
        # These cause pwnagotchi's log parser to throw errors like "time data 'CHG' does not match format"
        lines = text.split("\n")
        filtered_lines = []
        for line in lines:
            # Skip lines that start with bluetoothctl status markers
            stripped = line.strip()
            if not (
                stripped.startswith("[CHG]")
                or stripped.startswith("[DEL]")
                or stripped.startswith("[NEW]")
            ):
                filtered_lines.append(line)

        return "\n".join(filtered_lines)

    def _check_bluetooth_responsive(self):
        """Quick check if bluetoothctl is responsive"""
        try:
            result = subprocess.run(
                ["bluetoothctl", "show"],
                capture_output=True,
                timeout=self.SUBPROCESS_TIMEOUT_NORMAL,  # Short timeout for health check
                text=True,
            )
            return result.returncode == 0
        except Exception as e:
            logging.debug(f"[bt-tether] Bluetooth responsive check failed: {e}")
            return False

    def _restart_bluetooth_if_needed(self):
        """Restart Bluetooth service if it's unresponsive"""
        if not self._check_bluetooth_responsive():
            logging.warning("[bt-tether] Bluetooth appears hung, restarting service...")
            try:
                subprocess.run(
                    ["pkill", "-9", "bluetoothctl"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
                )
                subprocess.run(
                    ["systemctl", "restart", "bluetooth"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.SUBPROCESS_TIMEOUT_STANDARD,  # Reduced timeout for RPi Zero W2
                )
                time.sleep(self.OPERATION_MEDIUM_DELAY)  # Extra time on slow hardware
                self._log("INFO", "Bluetooth service restarted")
                return True
            except Exception as e:
                self._log("ERROR", f"Failed to restart Bluetooth: {e}")
                return False
        return True

    def _run_cmd(self, cmd, capture=False, timeout=None):
        """Run shell command with error handling and deadlock prevention"""
        if timeout is None:
            timeout = self.SUBPROCESS_TIMEOUT_LONG
        # Use lock to prevent multiple bluetoothctl commands from running simultaneously
        with self._bluetoothctl_lock:
            try:
                # Disable bluetoothctl color output to prevent ANSI codes in logs
                env = dict(os.environ)
                env["NO_COLOR"] = "1"  # Standard env var to disable colors
                env["TERM"] = "dumb"  # Make terminal report as non-color capable

                if capture:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=timeout, env=env
                    )
                    # Return combined output with ANSI codes stripped to prevent log parser errors
                    output = result.stdout + result.stderr
                    return self._strip_ansi_codes(output)
                else:
                    subprocess.run(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=timeout,
                        env=env,
                    )
                    return None
            except subprocess.TimeoutExpired:
                logging.error(
                    f"[bt-tether] Command timeout ({timeout}s): {' '.join(cmd)}"
                )
                # Kill hung bluetoothctl after timeout (only if it's a bluetoothctl command)
                if cmd and cmd[0] == "bluetoothctl":
                    try:
                        subprocess.run(
                            ["pkill", "-9", "bluetoothctl"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=2,
                        )
                        time.sleep(
                            self.PROCESS_CLEANUP_DELAY
                        )  # Brief pause to let process die
                    except Exception as e:
                        self._log("DEBUG", f"Process kill failed: {e}")
                return "Timeout"
            except Exception as e:
                logging.error(f"[bt-tether] Command failed: {' '.join(cmd)}")
                logging.error(f"[bt-tether] Exception: {e}")
                return None

    def _setup_network_dhcp(self, iface):
        """Setup network for bnep0 interface using dhclient"""
        try:
            self._log("INFO", f"Setting up network for {iface}...")

            # Ensure interface is up
            self._log("INFO", f"Ensuring {iface} is up...")
            subprocess.run(
                ["sudo", "ip", "link", "set", iface, "up"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )

            # Use dhclient directly (more reliable for Bluetooth PAN)
            return self._setup_dhclient(iface)

        except subprocess.TimeoutExpired:
            self._log("ERROR", "Network setup timed out")
            return False
        except Exception as e:
            self._log("ERROR", f"Network setup error: {e}")
            return False

    def _kill_dhclient_for_interface(self, iface):
        """Kill dhclient processes specifically managing the given interface.

        Uses PID-based targeting to avoid killing dhclient processes for other interfaces.
        Only kills processes where the interface appears as a separate argument.
        """
        try:
            # Get all dhclient PIDs
            result = subprocess.run(
                ["pidof", "dhclient"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
            )

            if result.returncode != 0 or not result.stdout.strip():
                # No dhclient processes running
                return

            pids = result.stdout.strip().split()
            killed_any = False

            for pid in pids:
                try:
                    # Get command line for this PID
                    ps_result = subprocess.run(
                        ["ps", "-p", pid, "-o", "args="],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=2,
                    )

                    if ps_result.returncode != 0:
                        continue

                    cmdline = ps_result.stdout.strip()

                    # Parse dhclient command line more carefully
                    # dhclient command format: dhclient [options] [interface]
                    # The interface is typically the last argument
                    args = cmdline.split()

                    # The interface must be the LAST argument and match EXACTLY
                    # This prevents matching "dhclient eth0" when looking for "eth0-backup"
                    # or "dhclient bnep0" matching a config file path containing "bnep0"
                    if args and args[-1] == iface:
                        self._log(
                            "DEBUG",
                            f"Killing dhclient PID {pid} for {iface} (cmdline: {cmdline})",
                        )
                        subprocess.run(
                            ["sudo", "kill", pid],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=3,
                        )
                        killed_any = True
                    else:
                        self._log(
                            "DEBUG",
                            f"Skipping PID {pid} - not managing {iface} (cmdline: {cmdline})",
                        )
                except Exception as e:
                    self._log("DEBUG", f"Error checking PID {pid}: {e}")
                    continue

            if killed_any:
                time.sleep(
                    self.OPERATION_SHORT_DELAY
                )  # Brief wait for processes to exit

        except Exception as e:
            self._log("DEBUG", f"Error in _kill_dhclient_for_interface: {e}")

    def _setup_dhclient(self, iface):
        """Request DHCP on interface"""
        try:
            self._log("INFO", f"Setting up {iface} for DHCP...")

            # Bring interface up
            subprocess.run(
                ["sudo", "ip", "link", "set", iface, "up"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )

            # Check which DHCP client is available
            has_dhcpcd = (
                subprocess.run(["which", "dhcpcd"], capture_output=True).returncode == 0
            )
            has_dhclient = (
                subprocess.run(["which", "dhclient"], capture_output=True).returncode
                == 0
            )

            self._log("INFO", f"Requesting DHCP on {iface}...")
            dhcp_success = False

            if has_dhcpcd:
                self._log("INFO", "Using dhcpcd...")
                # Release any existing lease first
                subprocess.run(
                    ["sudo", "dhcpcd", "-k", iface],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                time.sleep(self.DHCP_RELEASE_WAIT)
                # Request new lease
                result = subprocess.run(
                    ["sudo", "dhcpcd", "-4", "-n", iface],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=20,
                )
                if result.stdout.strip():
                    self._log("INFO", f"dhcpcd: {result.stdout.strip()}")
                if result.returncode == 0:
                    dhcp_success = True
                else:
                    self._log("WARNING", f"dhcpcd failed: {result.stderr.strip()}")

            elif has_dhclient:
                self._log("INFO", "Using dhclient...")
                # Kill any existing dhclient for this interface (PID-based targeting)
                self._kill_dhclient_for_interface(iface)
                time.sleep(self.DHCP_KILL_WAIT)

                # Request new lease with better error handling
                try:
                    result = subprocess.run(
                        ["sudo", "dhclient", "-4", "-v", iface],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=30,
                    )
                    combined = f"{result.stdout} {result.stderr}".strip()

                    # Check for common error messages
                    if "Network error: Software caused connection abort" in combined:
                        self._log("WARNING", "dhclient: Connection aborted by phone")
                        self._log(
                            "WARNING",
                            "📱 Make sure Bluetooth tethering is ENABLED on your phone!",
                        )
                        self._log(
                            "WARNING",
                            "📱 Settings → Network → Hotspot & tethering → Bluetooth tethering",
                        )
                    elif "DHCPDISCOVER" in combined and "No DHCPOFFERS" in combined:
                        self._log("WARNING", "dhclient: No DHCP response from phone")
                        self._log(
                            "WARNING",
                            "📱 Phone is not providing DHCP - enable Bluetooth tethering!",
                        )

                    # Only log dhclient output if there's an error
                    if result.returncode != 0 and combined:
                        # Truncate long output
                        self._log("INFO", f"dhclient: {combined[:200]}")

                    if result.returncode == 0:
                        dhcp_success = True
                    else:
                        self._log("WARNING", f"dhclient returned {result.returncode}")

                except subprocess.TimeoutExpired:
                    self._log("WARNING", "dhclient timed out after 30s")
                    # Kill hung dhclient (PID-based targeting)
                    try:
                        # Get all dhclient PIDs
                        result = subprocess.run(
                            ["pidof", "dhclient"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=3,
                        )

                        if result.returncode == 0 and result.stdout.strip():
                            pids = result.stdout.strip().split()

                            for pid in pids:
                                try:
                                    # Get command line for this PID
                                    ps_result = subprocess.run(
                                        ["ps", "-p", pid, "-o", "args="],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True,
                                        timeout=2,
                                    )

                                    if ps_result.returncode != 0:
                                        continue

                                    cmdline = ps_result.stdout.strip()

                                    # Check if this dhclient is managing our interface
                                    # The interface MUST be the last argument
                                    args = cmdline.split()
                                    if args and args[-1] == iface:
                                        self._log(
                                            "DEBUG",
                                            f"Force killing dhclient PID {pid} for {iface} (cmdline: {cmdline})",
                                        )
                                        subprocess.run(
                                            ["sudo", "kill", "-9", pid],
                                            stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL,
                                            timeout=3,
                                        )
                                    else:
                                        self._log(
                                            "DEBUG",
                                            f"Skipping force-kill PID {pid} - not managing {iface} (cmdline: {cmdline})",
                                        )
                                except Exception as e:
                                    self._log(
                                        "DEBUG", f"Error force-killing PID {pid}: {e}"
                                    )
                                    continue
                    except Exception as e:
                        self._log("DEBUG", f"Error in timeout dhclient cleanup: {e}")

            else:
                self._log(
                    "ERROR",
                    "No DHCP client found! Install dhclient: sudo apt install isc-dhcp-client",
                )
                return False

            # Check for IP with extended wait time (tethering may take time to fully start)
            ip_addr = None
            max_checks = 8  # Increased from 5 to give more time

            for attempt in range(max_checks):
                ip_result = subprocess.run(
                    ["ip", "addr", "show", iface],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                )

                if ip_result.returncode == 0:
                    ip_match = re.search(
                        r"inet\s+(\d+\.\d+\.\d+\.\d+)", ip_result.stdout
                    )
                    if ip_match:
                        ip_addr = ip_match.group(1)
                        if not ip_addr.startswith("169.254."):
                            self._log("INFO", f"✓ {iface} got IP: {ip_addr}")
                            break
                        else:
                            self._log(
                                "DEBUG", f"Link-local IP {ip_addr}, waiting for DHCP..."
                            )
                            ip_addr = None

                if attempt < max_checks - 1:
                    self._log("DEBUG", f"Waiting for IP... ({(attempt+1)*2}s)")
                    time.sleep(2)

            if ip_addr:
                self._verify_localhost_route()
                return True
            else:
                self._log("ERROR", f"❌ No IP on {iface} after {max_checks * 2}s")
                self._log("ERROR", "📱 Enable Bluetooth tethering on your phone!")
                self._log(
                    "ERROR",
                    "📱 Settings → Network & internet → Hotspot & tethering → Bluetooth tethering",
                )
                return False

        except Exception as e:
            logging.error(f"[bt-tether] Network setup error: {e}")
            return False

    def _verify_localhost_route(self):
        """Verify localhost routes correctly through loopback interface (critical for bettercap API)"""
        try:
            # Check localhost routing
            result = subprocess.run(
                ["ip", "route", "get", "127.0.0.1"],
                capture_output=True,
                text=True,
                timeout=3,
            )

            if result.returncode == 0:
                route_output = result.stdout.strip()
                # Localhost should use 'lo' interface or 'local' keyword
                if "lo" not in route_output and "local" not in route_output:
                    logging.warning(
                        f"[bt-tether] ⚠️  Localhost routing misconfigured: {route_output}"
                    )
                    logging.warning(
                        "[bt-tether] ⚠️  This may prevent bettercap API from working!"
                    )
                    logging.info("[bt-tether] Attempting to fix localhost route...")

                    # Ensure loopback interface is up
                    subprocess.run(
                        ["sudo", "ip", "link", "set", "lo", "up"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=3,
                    )

                    # Add explicit localhost route if missing
                    subprocess.run(
                        ["sudo", "ip", "route", "add", "127.0.0.0/8", "dev", "lo"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=3,
                    )

                    logging.info("[bt-tether] ✓ Localhost route protection applied")
                else:
                    logging.debug(f"[bt-tether] Localhost route OK: {route_output}")
            else:
                logging.warning("[bt-tether] Could not verify localhost routing")

        except Exception as e:
            logging.error(f"[bt-tether] Localhost route verification failed: {e}")

    def _check_internet_connectivity(self):
        """Check if internet is accessible via Bluetooth interface specifically"""
        try:
            # Get the BT interface
            bt_iface = self._get_pan_interface() or "bnep0"

            # First verify bnep0 has an IP - if not, no point testing connectivity
            ip_result = subprocess.run(
                ["ip", "addr", "show", bt_iface],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )

            if ip_result.returncode != 0:
                logging.warning(f"[bt-tether] {bt_iface} interface not found")
                return False

            ip_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", ip_result.stdout)
            if not ip_match or ip_match.group(1).startswith("169.254."):
                logging.warning(f"[bt-tether] {bt_iface} has no valid IP")
                return False

            bt_ip = ip_match.group(1)
            logging.info(f"[bt-tether] {bt_iface} has IP: {bt_ip}")

            # Log current routing table for diagnostics
            route_check = subprocess.run(
                ["ip", "route", "show"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if route_check.returncode == 0:
                logging.info(f"[bt-tether] Current routes:\n{route_check.stdout}")

            # Ping via the Bluetooth interface specifically
            logging.info(
                f"[bt-tether] Testing connectivity to 8.8.8.8 via {bt_iface}..."
            )
            result = subprocess.run(
                ["ping", "-c", "2", "-W", "3", "-I", bt_iface, "8.8.8.8"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                logging.info(f"[bt-tether] ✓ Ping to 8.8.8.8 successful")
                return True
            else:
                logging.warning(f"[bt-tether] Ping to 8.8.8.8 failed")
                logging.warning(f"[bt-tether] Ping stderr: {result.stderr}")
                logging.warning(f"[bt-tether] Ping stdout: {result.stdout}")

                # Try to ping the gateway to see if that works
                gateway_check = subprocess.run(
                    ["ip", "route", "show", "default"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                )
                if gateway_check.returncode == 0 and gateway_check.stdout:

                    match = re.search(r"default via ([\d.]+)", gateway_check.stdout)
                    if match:
                        gateway = match.group(1)
                        logging.info(
                            f"[bt-tether] Testing connectivity to gateway {gateway}..."
                        )
                        gw_result = subprocess.run(
                            ["ping", "-c", "2", "-W", "3", gateway],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=10,
                        )
                        if gw_result.returncode == 0:
                            logging.warning(
                                f"[bt-tether] Gateway ping works, but internet ping failed - possible NAT/firewall issue"
                            )
                        else:
                            logging.warning(
                                f"[bt-tether] Gateway ping also failed - phone may not be providing internet"
                            )

                return False
        except subprocess.TimeoutExpired:
            logging.warning(f"[bt-tether] Ping timeout - no internet connectivity")
            return False
        except Exception as e:
            logging.error(f"[bt-tether] Internet check error: {e}")
            return False

    def _pan_active(self):
        """Check if any PAN interface (bnep/bt-pan) is active - optimized for RPi Zero W2"""
        try:
            # More efficient: use ip link show instead of full ip a output
            result = subprocess.run(
                ["ip", "link", "show"],
                capture_output=True,
                text=True,
                timeout=3,  # Reduced timeout for efficiency
            )

            # Check for both bnep and bt-pan interfaces
            has_bnep = "bnep" in result.stdout
            has_bt_pan = "bt-pan" in result.stdout

            if has_bnep or has_bt_pan:
                logging.debug(
                    f"[bt-tether] Found PAN interface (bnep={has_bnep}, bt-pan={has_bt_pan})"
                )
                return True

            logging.debug("[bt-tether] No PAN interface found (bnep/bt-pan)")
            return False
        except Exception as e:
            logging.error(f"[bt-tether] Failed to check PAN: {e}")
            return False

    def _get_default_route_interface(self):
        """Get the network interface that has the default route (lowest metric)"""
        try:
            result = subprocess.check_output(
                ["ip", "route", "show", "default"], text=True, timeout=5
            )

            if not result:
                return None

            # Parse default route lines to find the one with lowest metric
            # Format: "default via 192.168.1.1 dev eth0 metric 100"

            routes = []
            for line in result.strip().split("\n"):
                if "default" in line:
                    # Extract interface name
                    dev_match = re.search(r"dev\s+(\S+)", line)
                    if dev_match:
                        iface = dev_match.group(1)

                        # Extract metric (default to 0 if not specified)
                        metric_match = re.search(r"metric\s+(\d+)", line)
                        metric = int(metric_match.group(1)) if metric_match else 0

                        routes.append((iface, metric))

            if not routes:
                return None

            # Sort by metric (lowest first) and return the interface
            routes.sort(key=lambda x: x[1])
            return routes[0][0]

        except Exception as e:
            logging.debug(f"[bt-tether] Failed to get default route: {e}")
            return None

    def _test_internet_connectivity(self):
        """Test internet connectivity and return detailed results"""
        try:
            result = {
                "ping_success": False,
                "dns_success": False,
                "bnep0_ip": None,
                "default_route": None,
                "dns_servers": None,
                "dns_error": None,
                "localhost_routes": None,
            }

            # Test ping to 8.8.8.8
            try:
                ping_result = subprocess.run(
                    ["ping", "-c", "2", "-W", "3", "8.8.8.8"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5,
                )
                result["ping_success"] = ping_result.returncode == 0
                logging.info(
                    f"[bt-tether] Ping test: {'Success' if result['ping_success'] else 'Failed'}"
                )
            except Exception as e:
                logging.warning(f"[bt-tether] Ping test error: {e}")

            # Test DNS resolution
            try:
                import socket

                # Try to resolve google.com using Python's socket library
                socket.gethostbyname("google.com")
                result["dns_success"] = True
                logging.info("[bt-tether] DNS test: Success")
            except socket.gaierror as e:
                result["dns_success"] = False
                result["dns_error"] = f"DNS resolution failed: {str(e)}"
                logging.warning(f"[bt-tether] DNS test failed: {e}")
            except Exception as e:
                result["dns_success"] = False
                result["dns_error"] = str(e)
                logging.warning(f"[bt-tether] DNS test error: {e}")

            # Get DNS servers from resolv.conf
            try:
                with open("/etc/resolv.conf", "r") as f:
                    resolv_content = f.read()
                    dns_servers = []
                    for line in resolv_content.split("\n"):
                        if line.strip().startswith("nameserver"):
                            dns_servers.append(line.strip().split()[1])
                    result["dns_servers"] = (
                        ", ".join(dns_servers) if dns_servers else "None"
                    )
                logging.info(f"[bt-tether] DNS servers: {result['dns_servers']}")
            except Exception as e:
                result["dns_servers"] = f"Error: {str(e)[:50]}"
                logging.warning(f"[bt-tether] Get DNS servers error: {e}")

            # Get bnep0 IP address
            try:
                ip_result = subprocess.run(
                    ["ip", "addr", "show", "bnep0"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                )
                if ip_result.returncode == 0:

                    ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", ip_result.stdout)
                    if ip_match:
                        result["bnep0_ip"] = ip_match.group(1)
                logging.info(f"[bt-tether] bnep0 IP: {result['bnep0_ip']}")
            except Exception as e:
                logging.warning(f"[bt-tether] Get bnep0 IP error: {e}")

            # Get default route
            try:
                route_result = subprocess.run(
                    ["ip", "route", "show", "default"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                )
                if route_result.returncode == 0 and route_result.stdout:
                    result["default_route"] = route_result.stdout.strip()
                logging.info(f"[bt-tether] Default route: {result['default_route']}")
            except Exception as e:
                logging.warning(f"[bt-tether] Get default route error: {e}")

            # Get localhost route - CRITICAL for bettercap API access
            try:
                localhost_result = subprocess.run(
                    ["ip", "route", "get", "127.0.0.1"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                )
                if localhost_result.returncode == 0 and localhost_result.stdout:
                    result["localhost_routes"] = localhost_result.stdout.strip()
                    # Localhost should use 'lo' interface
                    if (
                        "lo" not in result["localhost_routes"]
                        and "local" not in result["localhost_routes"]
                    ):
                        logging.warning(
                            f"[bt-tether] ⚠️  WARNING: Localhost not routing through 'lo' interface!"
                        )
                        logging.warning(
                            f"[bt-tether] ⚠️  This may prevent bettercap API from working: {result['localhost_routes']}"
                        )
                    else:
                        logging.info(
                            f"[bt-tether] Localhost route: {result['localhost_routes']}"
                        )
                else:
                    result["localhost_routes"] = "Error getting localhost route"
            except Exception as e:
                result["localhost_routes"] = f"Error: {str(e)}"
                logging.warning(f"[bt-tether] Get localhost route error: {e}")

            return result

        except Exception as e:
            logging.error(f"[bt-tether] Internet connectivity test error: {e}")
            return {
                "ping_success": False,
                "dns_success": False,
                "bnep0_ip": None,
                "default_route": None,
                "dns_servers": None,
                "dns_error": str(e),
            }

    def _get_pan_interface(self):
        """Get the name of the Bluetooth PAN interface if it exists"""
        try:
            out = subprocess.check_output(["ip", "link"], text=True, timeout=5)
            # Look for bnep or bt-pan interface names
            for line in out.split("\n"):
                if "bnep" in line or "bt-pan" in line:
                    # Extract interface name (e.g., "2: bnep0:" -> "bnep0")
                    parts = line.split(":")
                    if len(parts) >= 2:
                        iface = parts[1].strip()
                        return iface
            return None
        except Exception as e:
            logging.error(f"[bt-tether] Failed to get PAN interface: {e}")
            return None

    def _get_interface_ip(self, iface):
        """Get IP address of a network interface"""
        try:

            result = subprocess.check_output(
                ["ip", "-4", "addr", "show", iface], text=True, timeout=5
            )
            # Look for inet address (e.g., "inet 192.168.44.123/24")
            match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", result)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            logging.debug(f"[bt-tether] Failed to get IP for {iface}: {e}")
            return None

    def _pair_device_interactive(self, mac, needs_discovery=True):
        """Pair device - persistent agent will handle the dialog.

        Args:
            needs_discovery: True if BlueZ's device cache was wiped (e.g. after 'remove')
                             and a fresh scan is required before pairing.
                             False if the device is still present in BlueZ from the
                             background scan (new device, no remove was called).
        """
        try:
            logging.info(f"[bt-tether] Starting pairing with {mac}...")

            with self.lock:
                self.message = "Scanning for phone..."

            # First ensure Bluetooth is powered on and in pairable mode
            self._run_cmd(["bluetoothctl", "power", "on"], capture=True)
            time.sleep(self.DEVICE_OPERATION_DELAY)
            self._run_cmd(["bluetoothctl", "pairable", "on"], capture=True)
            self._run_cmd(["bluetoothctl", "discoverable", "on"], capture=True)
            time.sleep(self.DEVICE_OPERATION_DELAY)

            # Quick health check - ensure bluetoothctl is responsive before pairing
            if not self._check_bluetooth_responsive():
                logging.warning(
                    "[bt-tether] Bluetooth service appears unresponsive - attempting recovery"
                )
                self._restart_bluetooth_if_needed()
                time.sleep(self.OPERATION_MEDIUM_DELAY)

            if not needs_discovery:
                # Device is still in BlueZ's cache from the background scan — pair immediately
                logging.info(
                    f"[bt-tether] Device {mac} already in BlueZ cache, no discovery needed"
                )
                device_visible = True
            else:
                # BlueZ cache was wiped (after 'remove') — open an interactive bluetoothctl
                # session and watch for the "[NEW] Device <mac>" event in real time.
                # This reacts within milliseconds of the device reappearing instead of
                # polling every second.
                discovery_timeout = self.PAIRING_SCAN_WAIT_TIMEOUT
                logging.info(
                    f"[bt-tether] Waiting for {mac} to reappear after remove (up to {discovery_timeout}s)..."
                )

                device_visible = False
                scan_start = time.time()
                scan_process = None
                try:
                    env = dict(os.environ, TERM="dumb", NO_COLOR="1")
                    scan_process = subprocess.Popen(
                        ["bluetoothctl"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        env=env,
                    )
                    scan_process.stdin.write("scan on\n")
                    scan_process.stdin.flush()

                    target_mac = mac.upper()
                    while time.time() - scan_start < discovery_timeout:
                        try:
                            import select

                            ready = select.select([scan_process.stdout], [], [], 0.5)
                            if ready[0]:
                                line = scan_process.stdout.readline()
                                if not line:
                                    break
                                clean_line = self.SCAN_ANSI_PATTERN.sub(
                                    "", line.strip()
                                )
                                if "[NEW]" in clean_line and "Device" in clean_line:
                                    m = self.SCAN_MAC_PATTERN.search(clean_line)
                                    if m and m.group(1).upper() == target_mac:
                                        device_visible = True
                                        elapsed = time.time() - scan_start
                                        logging.info(
                                            f"[bt-tether] Device {mac} reappeared after {elapsed:.1f}s"
                                        )
                                        break
                        except Exception:
                            pass
                finally:
                    # Stop scan and close bluetoothctl
                    try:
                        self._run_cmd(
                            ["bluetoothctl", "scan", "off"], capture=True, timeout=3
                        )
                        time.sleep(self.SCAN_STOP_DELAY)
                    except Exception:
                        pass
                    if scan_process:
                        try:
                            scan_process.stdin.write("quit\n")
                            scan_process.stdin.flush()
                            scan_process.wait(timeout=self.SUBPROCESS_TIMEOUT_MEDIUM)
                        except Exception:
                            try:
                                scan_process.kill()
                                scan_process.wait(timeout=self.SUBPROCESS_TIMEOUT_SHORT)
                            except Exception:
                                pass

                if not device_visible:
                    elapsed = time.time() - scan_start
                    logging.warning(
                        f"[bt-tether] Device {mac} not found after {elapsed:.1f}s - attempting pair anyway"
                    )

            with self.lock:
                self.message = "Phone found! Initiating pairing..."

            # Start monitoring agent log for passkey in background
            passkey_found = threading.Event()
            monitor_thread = threading.Thread(
                target=self._monitor_agent_log_for_passkey,
                args=(passkey_found,),
                daemon=True,
            )
            monitor_thread.start()

            # Initiate pairing from Pwnagotchi side - agent will show passkey dialog on phone
            logging.info(f"[bt-tether] Running: bluetoothctl pair {mac}")
            logging.info(
                f"[bt-tether] ⚠️  Pairing dialog will appear on your phone - confirm the passkey!"
            )

            try:
                # Use subprocess.Popen to capture output in real-time
                env = dict(os.environ)
                env["NO_COLOR"] = "1"
                env["TERM"] = "dumb"

                # Start pairing process
                process = subprocess.Popen(
                    ["bluetoothctl", "pair", mac],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    bufsize=1,  # Line buffered
                )

                try:
                    # Read output in real-time to capture passkey immediately
                    output_lines = []
                    passkey_found_in_output = False

                    while True:
                        line = process.stdout.readline()
                        if not line:
                            # Process finished
                            break

                        output_lines.append(line)
                        clean_line = self._strip_ansi_codes(line.strip())

                        # Look for passkey in real-time
                        if not passkey_found_in_output:
                            passkey_match = re.search(
                                r"passkey\s+(\d{6})", clean_line, re.IGNORECASE
                            )
                            if passkey_match:
                                self.current_passkey = passkey_match.group(1)
                                passkey_found_in_output = True
                                self._log(
                                    "WARNING",
                                    f"🔑 PASSKEY: {self.current_passkey} - Confirm on phone!",
                                )
                                logging.info(
                                    f"[bt-tether] 🔑 PASSKEY: {self.current_passkey} captured from pair command"
                                )

                                # Update status message so it shows prominently in web UI
                                with self.lock:
                                    self.status = self.STATE_PAIRING
                                    self.message = f"🔑 PASSKEY: {self.current_passkey}\n\nVerify this matches on your phone, then tap PAIR!"

                            elif (
                                "Confirm passkey" in clean_line
                                or "DisplayPasskey" in clean_line
                            ):
                                # Try alternative patterns
                                display_match = re.search(r"(\d{6})", clean_line)
                                if display_match:
                                    self.current_passkey = display_match.group(1)
                                    passkey_found_in_output = True
                                    self._log(
                                        "WARNING",
                                        f"🔑 PASSKEY: {self.current_passkey} - Confirm on phone!",
                                    )
                                    logging.info(
                                        f"[bt-tether] 🔑 PASSKEY: {self.current_passkey} captured from pair command"
                                    )

                                    # Update status message so it shows prominently in web UI
                                    with self.lock:
                                        self.status = self.STATE_PAIRING
                                        self.message = f"🔑 PASSKEY: {self.current_passkey}\n\nVerify this matches on your phone, then tap PAIR!"

                    # Wait for process to complete with passkey timeout
                    # Phone usually times out after 30-45s if passkey not confirmed
                    returncode = process.wait(timeout=self.PAIRING_PASSKEY_TIMEOUT)
                    output = "".join(output_lines)
                    clean_output = self._strip_ansi_codes(output)

                    # Check if pairing succeeded
                    if (
                        "Pairing successful" in clean_output
                        or "AlreadyExists" in clean_output
                    ):
                        logging.info(f"[bt-tether] ✓ Pairing successful!")
                        # Clear passkey after successful pairing
                        self.current_passkey = None
                        return True
                    elif returncode == 0:
                        # Command succeeded but output unclear - check status
                        time.sleep(self.DEVICE_OPERATION_LONGER_DELAY)
                        pair_status = self._check_pair_status(mac)
                        if pair_status["paired"]:
                            logging.info(f"[bt-tether] ✓ Pairing successful!")
                            # Clear passkey after successful pairing
                            self.current_passkey = None
                            return True

                    # Diagnose specific failure types
                    error_hints = ""
                    if (
                        "Authentication failed" in clean_output
                        or "0x05" in clean_output
                    ):
                        error_hints = "\n💡 IMPORTANT: Go to your phone's Bluetooth settings and FORGET/UNPAIR this device first!\n   Then try pairing again. (0x05 = phone has stale cached credentials)"
                    elif "Connection refused" in clean_output:
                        error_hints = "\n💡 Hint: Device not found. Make sure phone's Bluetooth is ON and discoverable."
                    elif (
                        "AlreadyExists" not in clean_output
                        and "Pairing successful" not in clean_output
                    ):
                        # Passkey on phone not confirmed or timed out
                        if not passkey_found_in_output:
                            error_hints = "\n💡 Hint: No passkey appeared. Check Bluetooth permissions or restart phone's Bluetooth."
                        else:
                            error_hints = f"\n💡 Hint: Passkey {self.current_passkey} was shown but not confirmed on phone."

                    logging.error(
                        f"[bt-tether] Pairing failed: {clean_output}{error_hints}"
                    )
                    self._log("ERROR", f"Pairing failed. {error_hints.lstrip()}")
                    return False

                finally:
                    # Ensure process stdout is closed to prevent resource leak
                    try:
                        if process.stdout:
                            process.stdout.close()
                    except Exception:
                        pass
                    # Kill process if still running
                    try:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=self.SUBPROCESS_TIMEOUT_MEDIUM)
                    except Exception:
                        pass

            except subprocess.TimeoutExpired:
                logging.error(
                    f"[bt-tether] Pairing timeout ({self.PAIRING_PASSKEY_TIMEOUT}s) - phone didn't respond or confirm passkey"
                )
                self._log(
                    "ERROR",
                    f"Pairing timeout - Try: 1) Confirm passkey on phone, or 2) Forget device in phone's Bluetooth settings, then retry",
                )
                return False

        except Exception as e:
            logging.error(f"[bt-tether] Pairing error: {e}")
            return False

    def _get_current_ip(self):
        """Get the current IP address from the Bluetooth PAN interface only"""
        try:
            # Only get IP from bluetooth interface - don't fall back to LAN/WiFi
            # since we're advertising the BT tethering IP
            pan_iface = self._get_pan_interface()
            if pan_iface:
                ip = self._get_interface_ip(pan_iface)
                if ip and not ip.startswith("169.254."):  # Exclude link-local
                    self._log("DEBUG", f"Found BT IP {ip} on {pan_iface}")
                    return ip

            # Also check bnep0 explicitly in case _get_pan_interface missed it
            ip = self._get_interface_ip("bnep0")
            if ip and not ip.startswith("169.254."):
                self._log("DEBUG", f"Found BT IP {ip} on bnep0")
                return ip

            self._log("DEBUG", "No IP address found on Bluetooth interface")
            return None
        except Exception as e:
            self._log("ERROR", f"Failed to get BT IP: {e}")
            return None

    def _get_pwnagotchi_name(self):
        """Get pwnagotchi name"""
        try:
            return pwnagotchi.name()
        except Exception as e:
            self._log("DEBUG", f"Failed to get pwnagotchi name: {e}")
        return "pwnagotchi"

    def _set_device_name(self):
        """Set the Bluetooth device name via bluetoothctl"""
        try:
            pwnagotchi_name = self._get_pwnagotchi_name()
            cmd = ["bluetoothctl", "set-alias", pwnagotchi_name]
            self._run_cmd(cmd, timeout=5)
            self._log("INFO", f"Set Bluetooth device name to: {pwnagotchi_name}")
        except Exception as e:
            self._log("WARNING", f"Failed to set device name: {e}")

    def _connect_nap_dbus(self, mac):
        """Connect to NAP service using DBus directly"""
        try:
            if not DBUS_AVAILABLE:
                logging.error("[bt-tether] dbus module not available")
                return False

            logging.info("[bt-tether] Connecting to system bus...")
            bus = dbus.SystemBus()
            manager = dbus.Interface(
                bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager"
            )
            logging.info("[bt-tether] System bus connected")

            # Find the device object path
            logging.info("[bt-tether] Searching for device in BlueZ...")
            objects = manager.GetManagedObjects()
            device_path = None
            for path, interfaces in objects.items():
                if "org.bluez.Device1" in interfaces:
                    props = interfaces["org.bluez.Device1"]
                    if props.get("Address") == mac:
                        device_path = path
                        logging.info(f"[bt-tether] Found device at path: {device_path}")
                        break

            if not device_path:
                logging.error(
                    f"[bt-tether] Device {mac} not found in BlueZ managed objects"
                )
                return False

            # Connect to NAP service UUID
            logging.info(
                f"[bt-tether] Connecting to NAP profile (UUID: {self.NAP_UUID})..."
            )
            device = dbus.Interface(
                bus.get_object("org.bluez", device_path), "org.bluez.Device1"
            )

            # Set a timeout for the ConnectProfile call to prevent hanging
            try:
                device.ConnectProfile(self.NAP_UUID, timeout=30)
                logging.info(
                    f"[bt-tether] ✓ NAP profile connected successfully via DBus"
                )
                return True
            except dbus.exceptions.DBusException as dbus_err:
                error_msg = str(dbus_err)
                logging.error(f"[bt-tether] DBus NAP connection failed: {dbus_err}")

                # Check for authentication/pairing errors - if phone was unpaired, remove pairing on Pwnagotchi side too
                # BUT: Don't remove for tethering-disabled errors (br-connection-create-socket, br-connection-profile-unavailable)
                # AND: Don't remove for transient errors (page-timeout, host-down) - phone may just be out of range
                if (
                    "Authentication Rejected" in error_msg
                    or "Connection refused" in error_msg
                ):
                    self._log(
                        "WARNING",
                        "⚠️  Device may have been unpaired from phone - removing stale pairing",
                    )
                    # Remove the pairing to prevent repeated failed connection attempts
                    try:
                        self._run_cmd(["bluetoothctl", "remove", mac], timeout=5)
                        self._log(
                            "INFO",
                            "Removed stale pairing - use web UI to re-pair if needed",
                        )
                        # Also clear the phone_mac to force re-scanning
                        with self.lock:
                            self.phone_mac = ""
                            self.options["mac"] = ""
                    except Exception as e:
                        logging.debug(f"Failed to remove pairing: {e}")
                elif (
                    "br-connection-page-timeout" in error_msg
                    or "br-connection-unknown" in error_msg
                    or "Host is down" in error_msg
                ):
                    # Transient errors - phone may be out of range or BT off, don't remove pairing
                    self._log(
                        "WARNING",
                        "⚠️  Phone not reachable (out of range or BT off) - will retry later",
                    )

                # Check for common errors and provide helpful hints
                if (
                    "br-connection-create-socket" in error_msg
                    or "br-connection-profile-unavailable" in error_msg
                ):
                    self._log(
                        "ERROR",
                        "⚠️  Bluetooth tethering is NOT enabled on your phone!",
                    )
                    self._log(
                        "ERROR",
                        "Go to Settings → Network & internet → Hotspot & tethering → Enable 'Bluetooth tethering'",
                    )
                elif "NoReply" in error_msg or "Did not receive a reply" in error_msg:
                    self._log(
                        "ERROR",
                        "⚠️  Phone's Bluetooth is not responding to connection requests",
                    )
                    self._log(
                        "ERROR",
                        "📱 On your phone: Forget/unpair this device in Bluetooth settings",
                    )
                    self._log(
                        "ERROR",
                        "🔄 Then toggle Bluetooth tethering OFF and back ON",
                    )
                    self._log(
                        "ERROR",
                        "🔌 Finally, reconnect from the web UI to re-pair",
                    )
                elif "br-connection-busy" in error_msg or "InProgress" in error_msg:
                    self._log(
                        "ERROR",
                        "⚠️  Bluetooth connection is busy, wait a moment and try again",
                    )

                return False

        except ImportError as e:
            logging.error(f"[bt-tether] python3-dbus not installed: {e}")
            logging.error("[bt-tether] Run: sudo apt-get install -y python3-dbus")
            return False
        except Exception as e:
            error_msg = str(e)
            logging.error(f"[bt-tether] NAP connection error: {type(e).__name__}: {e}")

            logging.error(f"[bt-tether] Traceback: {traceback.format_exc()}")
            return False
