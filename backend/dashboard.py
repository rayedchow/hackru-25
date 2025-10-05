"""
Web dashboard HTML for monitoring.
Shows live feed and scroll detection.
"""

HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>BrainRot Monitor</title>
  <style>
    body {
      background: #0e0e0f;
      color: #e9e9e9;
      font-family: ui-monospace, monospace;
      margin: 0;
      padding: 16px;
    }
    .container {
      display: flex;
      gap: 16px;
      align-items: flex-start;
    }
    .card {
      background: #161617;
      border: 1px solid #2a2a2c;
      border-radius: 12px;
      padding: 16px;
    }
    #preview {
      max-height: 70vh;
      max-width: 50vw;
      border: 1px solid #2a2a2c;
      border-radius: 8px;
    }
    .info {
      min-width: 360px;
    }
    .row {
      display: flex;
      justify-content: space-between;
      padding: 8px 0;
      border-bottom: 1px dotted #2a2a2c;
    }
    .label {
      color: #9aa0a6;
    }
    .badge {
      display: inline-block;
      padding: 4px 12px;
      border-radius: 999px;
      font-size: 12px;
      border: 1px solid;
      margin-top: 12px;
    }
    .success {
      color: #00ff88;
      border-color: #00ff88;
    }
    .warning {
      color: #ffd400;
      border-color: #ffd400;
    }
    .scroll-indicator {
      display: none;
      color: #00d4ff;
      border-color: #00d4ff;
    }
  </style>
</head>
<body>
  <h2>🧠 BrainRot Monitor</h2>
  <div class="container">
    <img id="preview" class="card" alt="Waiting for frames..."/>
    <div class="card info">
      <div class="row">
        <span class="label">Session ID</span>
        <span id="session">—</span>
      </div>
      <div class="row">
        <span class="label">Frames</span>
        <span id="frames">0</span>
      </div>
      <div class="row">
        <span class="label">App</span>
        <strong id="app">UNKNOWN</strong>
      </div>
      <div class="row">
        <span class="label">Last Event</span>
        <span id="event">—</span>
      </div>
      <div>
        <span id="scrollBadge" class="badge scroll-indicator">🔄 SCROLL</span>
        <span id="status" class="badge warning">Connecting...</span>
      </div>
    </div>
  </div>

<script>
let ws;
let frameCount = 0;
let lastScrollTime = 0;

function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  
  ws.onopen = () => {
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').className = 'badge success';
  };
  
  ws.onclose = () => {
    document.getElementById('status').textContent = 'Reconnecting...';
    document.getElementById('status').className = 'badge warning';
    setTimeout(connect, 1500);
  };
  
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    
    if (data.type === 'frame') {
      frameCount++;
      document.getElementById('frames').textContent = frameCount;
      document.getElementById('preview').src = 'data:image/jpeg;base64,' + data.image;
      document.getElementById('app').textContent = (data.app || 'unknown').toUpperCase();
      document.getElementById('session').textContent = data.session_id.substring(0, 8);
      
      if (data.did_scroll) {
        const now = Date.now();
        if (now - lastScrollTime > 500) {
          lastScrollTime = now;
          const badge = document.getElementById('scrollBadge');
          badge.style.display = 'inline-block';
          document.getElementById('event').textContent = 'Scroll detected';
          setTimeout(() => { badge.style.display = 'none'; }, 1000);
        }
      }
    }
  };
}

connect();
</script>
</body>
</html>"""
