import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';

class BackendProcessDataSource {
  Process? _backendProcess;

  File? _findStandaloneBackendExecutable() {
    try {
      final String execName = Platform.isWindows ? 'app.exe' : 'app';
      final String altExecName = Platform.isWindows ? 'backend.exe' : 'backend';

      // Candidates list
      final List<String> pathsToCheck = [];

      // 1. Next to the running Flutter app executable
      try {
        final appDir = File(Platform.resolvedExecutable).parent.path;
        pathsToCheck.add('$appDir/$execName');
        pathsToCheck.add('$appDir/$altExecName');
        pathsToCheck.add('$appDir/backend/$execName');
        pathsToCheck.add('$appDir/backend/$altExecName');
      } catch (_) {}

      // 2. In current working directory
      try {
        final currentDir = Directory.current.path;
        pathsToCheck.add('$currentDir/$execName');
        pathsToCheck.add('$currentDir/$altExecName');
        pathsToCheck.add('$currentDir/backend/$execName');
        pathsToCheck.add('$currentDir/backend/$altExecName');
      } catch (_) {}

      for (final path in pathsToCheck) {
        final file = File(path);
        if (file.existsSync()) {
          return file;
        }
      }
    } catch (e) {
      debugPrint("[AUTO-START] Error searching for standalone backend: $e");
    }
    return null;
  }

  Directory? _findBackendDirectory() {
    try {
      Directory current = Directory.current;
      for (int i = 0; i < 5; i++) {
        final appPy = File('${current.path}/app.py');
        if (appPy.existsSync()) {
          return current;
        }
        final parent = current.parent;
        if (parent.path == current.path) break;
        current = parent;
      }
    } catch (e) {
      debugPrint("[AUTO-START] Error traversing directories: $e");
    }
    return null;
  }

  Future<String> _findWorkingPythonExecutable(Directory backendDir) async {
    final List<String> candidates = [
      'D:\\GOOGLE_TAKEOUT_RAG\\venv\\Scripts\\python.exe', // Hardcoded verified path
      'D:\\GOOGLE_TAKEOUT_RAG\\.venv\\Scripts\\python.exe',
      '${backendDir.path}/venv/Scripts/python.exe',
      '${backendDir.path}/.venv/Scripts/python.exe',
      'python',
    ];
    if (!Platform.isWindows) {
      candidates.clear();
      candidates.addAll([
        '${backendDir.path}/.venv/bin/python',
        '${backendDir.path}/venv/bin/python',
        'python3',
        'python',
      ]);
    }

    for (final path in candidates) {
      final isLocalFile = path.contains('/') || path.contains('\\');
      if (isLocalFile && !File(path).existsSync()) {
        continue;
      }

      debugPrint("[AUTO-START] Verifying dependencies on candidate Python: $path");
      try {
        final result = await Process.run(path, ['-c', 'import pandas, fastapi'])
            .timeout(const Duration(milliseconds: 2000));
        if (result.exitCode == 0) {
          debugPrint("[AUTO-START] Found working Python interpreter: $path");
          return path;
        } else {
          debugPrint(
              "[AUTO-START] Candidate $path failed dependency check (exit code ${result.exitCode}).");
        }
      } catch (e) {
        debugPrint("[AUTO-START] Candidate $path not executable: $e");
      }
    }

    debugPrint(
        "[AUTO-START] WARNING: No Python interpreter passed the check. Falling back to system default.");
    return Platform.isWindows ? 'python' : 'python3';
  }

  Future<void> cleanPortConflict() async {
    if (kIsWeb) return;
    debugPrint("[AUTO-START] Clearing any stale/orphaned processes on port 8000...");
    try {
      if (Platform.isWindows) {
        await Process.run('powershell', [
          '-Command',
          'Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue'
        ]).timeout(const Duration(seconds: 2));
      } else {
        await Process.run('sh', [
          '-c',
          'kill -9 \$(lsof -t -i:8000) 2>/dev/null || true'
        ]).timeout(const Duration(seconds: 2));
      }
      debugPrint("[AUTO-START] Port 8000 cleared.");
      await Future.delayed(const Duration(milliseconds: 300));
    } catch (e) {
      debugPrint("[AUTO-START] Warning clearing port 8000: $e");
    }
  }

  Future<void> startProcess({
    required void Function(String) onLog,
    required void Function(int) onExit,
  }) async {
    if (kIsWeb) return;

    final standaloneExe = _findStandaloneBackendExecutable();

    if (standaloneExe != null) {
      onLog("[AUTO-START] Found standalone compiled backend: ${standaloneExe.path}");
      onLog("[AUTO-START] Spawning standalone compiled process...");

      try {
        _backendProcess = await Process.start(
          standaloneExe.path,
          [],
          workingDirectory: standaloneExe.parent.path,
        );
      } catch (e) {
        onLog("[AUTO-START] EXCEPTION while spawning standalone backend: $e");
        rethrow;
      }
    } else {
      onLog("[AUTO-START] No standalone backend binary found. Falling back to development source mode.");
      final backendDir = _findBackendDirectory();
      if (backendDir == null) {
        onLog("[AUTO-START] ERROR: Could not locate backend root folder containing 'app.py' within parent tree.");
        throw Exception("Root directory with app.py not found");
      }

      final pythonExecutable = await _findWorkingPythonExecutable(backendDir);
      onLog("[AUTO-START] Found backend root: ${backendDir.path}");
      onLog("[AUTO-START] Selected Python executable: $pythonExecutable");
      onLog("[AUTO-START] Spawning FastAPI process: $pythonExecutable app.py");

      try {
        _backendProcess = await Process.start(
          pythonExecutable,
          ['app.py'],
          workingDirectory: backendDir.path,
        );
      } catch (e) {
        onLog("[AUTO-START] EXCEPTION while spawning backend process: $e");
        rethrow;
      }
    }

    _backendProcess!.stdout
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen((line) {
      onLog("[STDOUT] $line");
    });

    _backendProcess!.stderr
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen((line) {
      onLog("[STDERR] $line");
    });

    _backendProcess!.exitCode.then((code) {
      onLog("[PROCESS] Backend process exited with code $code");
      onExit(code);
    });
  }

  void shutdownProcess() {
    if (_backendProcess != null) {
      debugPrint("[AUTO-START] Shutting down background backend process...");
      _backendProcess!.kill();
      _backendProcess = null;
    }
  }
}
