"""
Webtop Ubuntu - Web-based Linux Desktop Environment
Flask backend with WebSocket terminal and file management API
"""
import os
import sys
import json
import subprocess
import threading
import queue
import signal
import shutil
import platform
import psutil
import select
import pty
import struct
import fcntl
import termios
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Store active terminal sessions
terminal_sessions = {}

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/system-info')
def system_info():
    """Get system information for the About dialog"""
    try:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return jsonify({
            'hostname': platform.node() or 'webtop-ubuntu',
            'os': 'Ubuntu 22.04 LTS (Webtop)',
            'kernel': platform.release(),
            'architecture': platform.machine(),
            'cpu': platform.processor() or 'Virtual CPU',
            'cpu_count': psutil.cpu_count(),
            'cpu_percent': psutil.cpu_percent(interval=0.5),
            'memory_total': mem.total,
            'memory_used': mem.used,
            'memory_percent': mem.percent,
            'disk_total': disk.total,
            'disk_used': disk.used,
            'disk_percent': disk.percent,
            'uptime': int(datetime.now().timestamp() - psutil.boot_time()),
            'python_version': platform.python_version()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/files')
@app.route('/api/files/<path:filepath>')
def list_files(filepath=''):
    """List files in a directory"""
    base = os.path.expanduser('~')
    target = os.path.normpath(os.path.join(base, filepath))
    if not target.startswith(base) and target != '/':
        target = base
    if not os.path.exists(target):
        return jsonify({'error': 'Path not found'}), 404
    if os.path.isfile(target):
        try:
            with open(target, 'r', errors='replace') as f:
                content = f.read(100000)
            return jsonify({'type': 'file', 'name': os.path.basename(target), 'path': target, 'content': content, 'size': os.path.getsize(target), 'modified': os.path.getmtime(target)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    items = []
    try:
        for entry in sorted(os.scandir(target), key=lambda e: (not e.is_dir(), e.name.lower())):
            try:
                stat = entry.stat(follow_symlinks=False)
                items.append({'name': entry.name, 'path': entry.path, 'is_dir': entry.is_dir(follow_symlinks=False), 'is_link': entry.is_symlink(), 'size': stat.st_size if not entry.is_dir() else 0, 'modified': stat.st_mtime, 'permissions': oct(stat.st_mode)[-3:], 'hidden': entry.name.startswith('.')})
            except (PermissionError, OSError):
                items.append({'name': entry.name, 'path': entry.path, 'is_dir': entry.is_dir() if not entry.is_symlink() else False, 'is_link': entry.is_symlink(), 'size': 0, 'modified': 0, 'permissions': '---', 'hidden': entry.name.startswith('.')})
    except PermissionError:
        return jsonify({'error': 'Permission denied'}), 403
    return jsonify({'type': 'directory', 'path': target, 'parent': os.path.dirname(target), 'items': items})

@app.route('/api/files/save', methods=['POST'])
def save_file():
    data = request.json
    filepath = data.get('path', '')
    content = data.get('content', '')
    try:
        with open(filepath, 'w') as f:
            f.write(content)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/create', methods=['POST'])
def create_item():
    data = request.json
    path = data.get('path', '')
    item_type = data.get('type', 'file')
    try:
        if item_type == 'folder':
            os.makedirs(path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write('')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/delete', methods=['POST'])
def delete_item():
    data = request.json
    path = data.get('path', '')
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/processes')
def list_processes():
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status', 'username']):
        try:
            info = p.info
            procs.append({'pid': info['pid'], 'name': info['name'], 'cpu': round(info['cpu_percent'] or 0, 1), 'memory': round(info['memory_percent'] or 0, 1), 'status': info['status'], 'user': info['username'] or 'root'})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x['cpu'], reverse=True)
    return jsonify(procs[:100])

@app.route('/api/wallpapers')
def get_wallpapers():
    return jsonify([
        {'id': 'jammy', 'name': 'Jammy Jellyfish', 'gradient': 'linear-gradient(135deg, #2c001e 0%, #5e2750 30%, #e95420 100%)'},
        {'id': 'focal', 'name': 'Focal Fossa', 'gradient': 'linear-gradient(135deg, #1a0a2e 0%, #3d1a6e 50%, #6d28d9 100%)'},
        {'id': 'kinetic', 'name': 'Kinetic Kudu', 'gradient': 'linear-gradient(135deg, #0d1b2a 0%, #1b263b 40%, #415a77 100%)'},
        {'id': 'lunar', 'name': 'Lunar Lobster', 'gradient': 'linear-gradient(135deg, #1e3a5f 0%, #4a8ab5 50%, #87ceeb 100%)'},
        {'id': 'mantic', 'name': 'Mantic Minotaur', 'gradient': 'linear-gradient(220deg, #300a24 0%, #5e2750 50%, #e95420 100%)'},
        {'id': 'noble', 'name': 'Noble Numbat', 'gradient': 'linear-gradient(135deg, #0f380f 0%, #306230 50%, #8bac0f 100%)'},
    ])

# --- WebSocket Terminal ---

def set_winsize(fd, row, col, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

@socketio.on('terminal_open')
def handle_terminal_open(data=None):
    sid = request.sid
    if sid in terminal_sessions:
        handle_terminal_close()
    try:
        child_pid, fd = pty.openpty()
        pid = os.fork()
        if pid == 0:
            os.close(fd)
            os.setsid()
            child_fd = os.open(os.ttyname(child_pid), os.O_RDWR)
            os.close(child_pid)
            os.dup2(child_fd, 0)
            os.dup2(child_fd, 1)
            os.dup2(child_fd, 2)
            if child_fd > 2:
                os.close(child_fd)
            env = os.environ.copy()
            env['TERM'] = 'xterm-256color'
            env['SHELL'] = '/bin/bash'
            env['HOME'] = os.path.expanduser('~')
            env['COLORTERM'] = 'truecolor'
            os.execvpe('/bin/bash', ['/bin/bash', '--login'], env)
        else:
            os.close(child_pid)
            set_winsize(fd, 24, 80)
            terminal_sessions[sid] = {'fd': fd, 'pid': pid, 'active': True}
            def read_output():
                while sid in terminal_sessions and terminal_sessions[sid]['active']:
                    try:
                        r, _, _ = select.select([fd], [], [], 0.1)
                        if r:
                            output = os.read(fd, 4096)
                            if output:
                                socketio.emit('terminal_output', {'output': output.decode('utf-8', errors='replace')}, room=sid)
                            else:
                                break
                    except (OSError, IOError):
                        break
                socketio.emit('terminal_exit', {}, room=sid)
            thread = threading.Thread(target=read_output, daemon=True)
            thread.start()
            terminal_sessions[sid]['thread'] = thread
            emit('terminal_ready', {'message': 'Terminal connected'})
    except Exception as e:
        emit('terminal_error', {'error': str(e)})

@socketio.on('terminal_input')
def handle_terminal_input(data):
    sid = request.sid
    if sid in terminal_sessions:
        try:
            fd = terminal_sessions[sid]['fd']
            os.write(fd, data['input'].encode('utf-8'))
        except (OSError, IOError):
            pass

@socketio.on('terminal_resize')
def handle_terminal_resize(data):
    sid = request.sid
    if sid in terminal_sessions:
        try:
            fd = terminal_sessions[sid]['fd']
            set_winsize(fd, data.get('rows', 24), data.get('cols', 80))
        except (OSError, IOError):
            pass

@socketio.on('terminal_close')
def handle_terminal_close():
    sid = request.sid
    if sid in terminal_sessions:
        session = terminal_sessions.pop(sid)
        session['active'] = False
        try:
            os.close(session['fd'])
        except OSError:
            pass
        try:
            os.kill(session['pid'], signal.SIGTERM)
            os.waitpid(session['pid'], os.WNOHANG)
        except (OSError, ChildProcessError):
            pass

@socketio.on('disconnect')
def handle_disconnect():
    handle_terminal_close()

if __name__ == '__main__':
    print('\n' + '='*60)
    print('  Webtop Ubuntu - Web Desktop Environment')
    print('  Open http://localhost:5000 in your browser')
    print('='*60 + '\n')
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
