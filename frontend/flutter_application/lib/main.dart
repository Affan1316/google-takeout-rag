import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform, File, Directory, Process;
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import 'package:http/http.dart' as http;
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:file_picker/file_picker.dart';
import 'package:path_provider/path_provider.dart';

void main() {
  runApp(const AIHistoryApp());
}

class AIHistoryApp extends StatelessWidget {
  const AIHistoryApp({super.key});

  // ── Design Tokens ──
  // Background layers (darkest → lightest)
  static const _bgDeep    = Color(0xFF0A0E1A);  // scaffold
  static const _bgCard    = Color(0xFF141829);  // cards, dialogs
  static const _bgSurface = Color(0xFF1C2137);  // input bar, appbar

  // Accent palette
  static const _accentPrimary   = Color(0xFF7C6AFF); // primary indigo-violet
  static const _accentSecondary = Color(0xFF38BDF8); // sky-blue for AI/drift
  static const _accentTertiary  = Color(0xFF34D399); // emerald for success
  static const _accentWarm      = Color(0xFFF59E0B); // amber for uploads
  static const _accentCoral     = Color(0xFFFB7185); // coral-rose for errors/code

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'History AI Agent',
      theme: ThemeData(
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: _accentPrimary,
          brightness: Brightness.dark,
        ),
        scaffoldBackgroundColor: _bgDeep,
        cardColor: _bgCard,
        useMaterial3: true,
      ),
      home: const ChatScreen(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class ChatMessage {
  final String text;
  final bool isUser;
  final DateTime timestamp;
  final List<dynamic>? steps;

  ChatMessage({
    required this.text,
    required this.isUser,
    DateTime? timestamp,
    this.steps,
  }) : timestamp = timestamp ?? DateTime.now();

  Map<String, dynamic> toJson() => {
    'text': text,
    'isUser': isUser,
    'timestamp': timestamp.toIso8601String(),
    'steps': steps,
  };

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
    text: json['text'] as String,
    isUser: json['isUser'] as bool,
    timestamp: json['timestamp'] != null 
        ? DateTime.parse(json['timestamp'] as String) 
        : DateTime.now(),
    steps: json['steps'] as List<dynamic>?,
  );
}

class ChatSession {
  final String id;
  final String title;
  final DateTime lastActive;
  final List<ChatMessage> messages;

  ChatSession({
    required this.id,
    required this.title,
    required this.lastActive,
    required this.messages,
  });

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'lastActive': lastActive.toIso8601String(),
    'messages': messages.map((m) => m.toJson()).toList(),
  };

  factory ChatSession.fromJson(Map<String, dynamic> json) => ChatSession(
    id: json['id'] as String,
    title: json['title'] as String,
    lastActive: DateTime.parse(json['lastActive'] as String),
    messages: (json['messages'] as List<dynamic>)
        .map((m) => ChatMessage.fromJson(m as Map<String, dynamic>))
        .toList(),
  );
}

class DbCredentials {
  final String url;
  final String password;
  final String llmApiKey;

  DbCredentials({required this.url, required this.password, required this.llmApiKey});

  Map<String, dynamic> toJson() => {
    'url': url,
    'password': password,
    'llmApiKey': llmApiKey,
  };

  factory DbCredentials.fromJson(Map<String, dynamic> json) => DbCredentials(
    url: json['url'] as String? ?? '',
    password: json['password'] as String? ?? '',
    llmApiKey: json['llmApiKey'] as String? ?? '',
  );
}

class ChatHistoryService {
  static const String _fileName = 'chat_sessions.json';
  static const String _credsFileName = 'db_credentials.json';

  Future<File> _getHistoryFile() async {
    final directory = await getApplicationDocumentsDirectory();
    return File('${directory.path}/$_fileName');
  }

  Future<File> _getCredsFile() async {
    final directory = await getApplicationDocumentsDirectory();
    return File('${directory.path}/$_credsFileName');
  }

  Future<DbCredentials?> loadCredentials() async {
    try {
      final file = await _getCredsFile();
      if (!await file.exists()) {
        return null;
      }
      final contents = await file.readAsString();
      return DbCredentials.fromJson(jsonDecode(contents) as Map<String, dynamic>);
    } catch (e) {
      debugPrint('Error loading db credentials: $e');
      return null;
    }
  }

  Future<void> saveCredentials(DbCredentials creds) async {
    try {
      final file = await _getCredsFile();
      await file.writeAsString(jsonEncode(creds.toJson()));
    } catch (e) {
      debugPrint('Error saving db credentials: $e');
    }
  }

  Future<List<ChatSession>> loadSessions() async {
    try {
      final file = await _getHistoryFile();
      if (!await file.exists()) {
        return [];
      }
      final contents = await file.readAsString();
      final List<dynamic> jsonList = jsonDecode(contents);
      final sessions = jsonList.map((json) => ChatSession.fromJson(json as Map<String, dynamic>)).toList();
      
      // Sort sessions by lastActive (descending: newest first)
      sessions.sort((a, b) => b.lastActive.compareTo(a.lastActive));
      return sessions;
    } catch (e) {
      debugPrint('Error loading chat history: $e');
      return [];
    }
  }

  Future<void> saveSessions(List<ChatSession> sessions) async {
    try {
      final file = await _getHistoryFile();
      final List<Map<String, dynamic>> jsonList =
          sessions.map((s) => s.toJson()).toList();
      await file.writeAsString(jsonEncode(jsonList));
    } catch (e) {
      debugPrint('Error saving chat history: $e');
    }
  }
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _controller = TextEditingController();
  final List<ChatMessage> _messages = [];
  bool _isLoading = false;
  bool _isConnected = false;
  bool _isIndexing = false;
  String _indexingMessage = "Ready";
  bool _isConnectingDb = false;
  Timer? _statusTimer;

  // Local Storage & Chat Sessions State
  final ChatHistoryService _historyService = ChatHistoryService();
  List<ChatSession> _sessions = [];
  String? _currentSessionId;

  // Auto-Starting Backend & Console Logs State
  Process? _backendProcess;
  final List<String> _consoleLogs = [];
  String _serverStatus = "Initializing...";
  bool _isServerStarting = false;

  void _addLog(String line) {
    final timestamp = DateTime.now().toLocal().toString().substring(11, 19);
    final formattedLine = '[$timestamp] $line';
    debugPrint(formattedLine);
    if (mounted) {
      setState(() {
        if (_consoleLogs.length >= 500) {
          _consoleLogs.removeAt(0);
        }
        _consoleLogs.add(formattedLine);
      });
    } else {
      if (_consoleLogs.length >= 500) {
        _consoleLogs.removeAt(0);
      }
      _consoleLogs.add(formattedLine);
    }
  }

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
      _addLog("[AUTO-START] Error searching for standalone backend: $e");
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
      _addLog("[AUTO-START] Error traversing directories: $e");
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
      
      _addLog("[AUTO-START] Verifying dependencies on candidate Python: $path");
      try {
        final result = await Process.run(path, ['-c', 'import pandas, fastapi']).timeout(const Duration(milliseconds: 2000));
        if (result.exitCode == 0) {
          _addLog("[AUTO-START] Found working Python interpreter: $path");
          return path;
        } else {
          _addLog("[AUTO-START] Candidate $path failed dependency check (exit code ${result.exitCode}).");
        }
      } catch (e) {
        _addLog("[AUTO-START] Candidate $path not executable: $e");
      }
    }
    
    _addLog("[AUTO-START] WARNING: No Python interpreter passed the check. Falling back to system default.");
    return Platform.isWindows ? 'python' : 'python3';
  }

  Future<void> _checkAndStartBackend() async {
    if (kIsWeb) {
      setState(() {
        _serverStatus = "Unsupported on Web";
      });
      return;
    }
    
    _addLog("[AUTO-START] Checking if backend API server is already online...");
    bool backendAlreadyRunning = false;
    try {
      final response = await http.get(Uri.parse(_statusUrl)).timeout(const Duration(seconds: 1));
      if (response.statusCode == 200) {
        _addLog("[AUTO-START] Backend is already running manually.");
        backendAlreadyRunning = true;
        final data = jsonDecode(response.body);
        final bool dbConnected = data['database_connected'] ?? false;
        final bool backendIsIndexing = data['is_indexing'] ?? false;
        final String backendMessage = data['indexing_message'] ?? "Ready";
        
        setState(() {
          _isConnected = dbConnected;
          _isIndexing = backendIsIndexing;
          _indexingMessage = backendMessage;
          _serverStatus = dbConnected ? "Connected (External)" : "Database Offline";
        });
        
        _checkInitialStatus();
        
        // Auto-connect database in background if not connected yet
        if (!dbConnected) {
          _autoConnectDatabase();
        }
        return;
      }
    } catch (_) {
      // Backend is not running, proceed to auto-start sequence
    }
    
    // Force-clear any orphaned local processes on port 8000 to prevent conflicts and ensure a clean, fresh backend launch
    _addLog("[AUTO-START] Clearing any stale/orphaned processes on port 8000...");
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
      _addLog("[AUTO-START] Port 8000 cleared.");
      // Give a tiny moment for OS to release socket binding
      await Future.delayed(const Duration(milliseconds: 300));
    } catch (e) {
      _addLog("[AUTO-START] Warning clearing port 8000: $e");
    }
    
    setState(() {
      _isServerStarting = true;
      _serverStatus = "Starting...";
    });
    
    _addLog("[AUTO-START] Backend not found on port 8000. Initiating auto-start sequence...");
    final standaloneExe = _findStandaloneBackendExecutable();
    
    if (standaloneExe != null) {
      _addLog("[AUTO-START] Found standalone compiled backend: ${standaloneExe.path}");
      _addLog("[AUTO-START] Spawning standalone compiled process...");
      
      try {
        _backendProcess = await Process.start(
          standaloneExe.path,
          [],
          workingDirectory: standaloneExe.parent.path,
        );
        
        _backendProcess!.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
          _addLog("[STDOUT] $line");
        });
        
        _backendProcess!.stderr.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
          _addLog("[STDERR] $line");
        });
        
        _backendProcess!.exitCode.then((code) {
          _addLog("[PROCESS] Standalone backend exited with code $code");
          if (_isConnected || _isServerStarting) {
            setState(() {
              _isConnected = false;
              _isServerStarting = false;
              _serverStatus = "Exited ($code)";
            });
          }
        });
      } catch (e) {
        _addLog("[AUTO-START] EXCEPTION while spawning standalone backend: $e");
        setState(() {
          _isServerStarting = false;
          _serverStatus = "Error Spawning";
        });
        return;
      }
    } else {
      _addLog("[AUTO-START] No standalone backend binary found. Falling back to development source mode.");
      final backendDir = _findBackendDirectory();
      if (backendDir == null) {
        _addLog("[AUTO-START] ERROR: Could not locate backend root folder containing 'app.py' within parent tree.");
        setState(() {
          _isServerStarting = false;
          _serverStatus = "Root Not Found";
        });
        return;
      }
      
      final pythonExecutable = await _findWorkingPythonExecutable(backendDir);
      _addLog("[AUTO-START] Found backend root: ${backendDir.path}");
      _addLog("[AUTO-START] Selected Python executable: $pythonExecutable");
      _addLog("[AUTO-START] Spawning FastAPI process: $pythonExecutable app.py");
      
      try {
        _backendProcess = await Process.start(
          pythonExecutable,
          ['app.py'],
          workingDirectory: backendDir.path,
        );
        
        _backendProcess!.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
          _addLog("[STDOUT] $line");
        });
        
        _backendProcess!.stderr.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
          _addLog("[STDERR] $line");
        });
        
        _backendProcess!.exitCode.then((code) {
          _addLog("[PROCESS] Backend process exited with code $code");
          if (_isConnected || _isServerStarting) {
            setState(() {
              _isConnected = false;
              _isServerStarting = false;
              _serverStatus = "Exited ($code)";
            });
          }
        });
      } catch (e) {
        _addLog("[AUTO-START] EXCEPTION while spawning backend process: $e");
        setState(() {
          _isServerStarting = false;
          _serverStatus = "Error Spawning";
        });
        return;
      }
    }

    _addLog("[AUTO-START] Polling backend health endpoint...");
    bool serverCameOnline = false;
    http.Response? onlineResponse;
    
    // Increase polling attempts to 75 (~60 seconds max) to allow PyInstaller binaries enough time 
    // to extract runtime libraries and load heavy ML embedding weights on first boot.
    const int maxAttempts = 75;
    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
      await Future.delayed(const Duration(milliseconds: 800));
      if (!mounted) return;
      
      try {
        final response = await http.get(Uri.parse(_statusUrl)).timeout(const Duration(seconds: 1));
        if (response.statusCode == 200) {
          _addLog("[AUTO-START] Backend server successfully responded on port 8000!");
          serverCameOnline = true;
          onlineResponse = response;
          break;
        }
      } catch (_) {
        _addLog("[AUTO-START] Health check attempt $attempt/$maxAttempts: waiting for server...");
      }
    }
    
    if (serverCameOnline && onlineResponse != null) {
      final data = jsonDecode(onlineResponse.body);
      final bool dbConnected = data['database_connected'] ?? false;
      final bool backendIsIndexing = data['is_indexing'] ?? false;
      final String backendMessage = data['indexing_message'] ?? "Ready";
      
      setState(() {
        _isConnected = dbConnected;
        _isServerStarting = false;
        _isIndexing = backendIsIndexing;
        _indexingMessage = backendMessage;
        _serverStatus = dbConnected ? "Connected" : "Database Offline";
      });
      
      _checkInitialStatus();
      
      // Auto-connect database in background if not connected yet
      if (!dbConnected) {
        _autoConnectDatabase();
      }
    } else {
      _addLog("[AUTO-START] ERROR: Backend server failed to respond within timeout.");
      setState(() {
        _isServerStarting = false;
        _serverStatus = "Start Failed";
      });
    }
  }

  Future<void> _autoConnectDatabase() async {
    try {
      final creds = await _historyService.loadCredentials();
      if (creds != null && creds.url.isNotEmpty) {
        _addLog("[AUTO-CONNECT] Local credentials found. Autoconnecting in background...");
        await _connectToDatabase(creds.url, creds.password, creds.llmApiKey);
      } else {
        _addLog("[AUTO-CONNECT] No saved database credentials found.");
      }
    } catch (e) {
      _addLog("[AUTO-CONNECT] Exception during background auto-connect: $e");
    }
  }
  
  void _shutdownBackend() {
    if (_backendProcess != null) {
      _addLog("[AUTO-START] Shutting down background backend process...");
      _backendProcess!.kill();
      _backendProcess = null;
    }
  }

  void _showTerminalLogs() {
    final ScrollController terminalScrollController = ScrollController();
    
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (terminalScrollController.hasClients) {
        terminalScrollController.jumpTo(terminalScrollController.position.maxScrollExtent);
      }
    });

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (BuildContext context) {
        return StatefulBuilder(
          builder: (BuildContext context, StateSetter modalSetState) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (terminalScrollController.hasClients) {
                terminalScrollController.animateTo(
                  terminalScrollController.position.maxScrollExtent,
                  duration: const Duration(milliseconds: 200),
                  curve: Curves.easeOut,
                );
              }
            });

            return Container(
              height: MediaQuery.of(context).size.height * 0.7,
              decoration: const BoxDecoration(
                color: AIHistoryApp._bgDeep,
                borderRadius: BorderRadius.only(
                  topLeft: Radius.circular(24),
                  topRight: Radius.circular(24),
                ),
                border: Border(
                  top: BorderSide(color: Color(0xFF1E2648), width: 1.5),
                ),
              ),
              child: Column(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                    decoration: const BoxDecoration(
                      color: AIHistoryApp._bgSurface,
                      borderRadius: BorderRadius.only(
                        topLeft: Radius.circular(24),
                        topRight: Radius.circular(24),
                      ),
                      border: Border(bottom: BorderSide(color: Colors.white10, width: 0.5)),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 10,
                          height: 10,
                          decoration: const BoxDecoration(color: AIHistoryApp._accentCoral, shape: BoxShape.circle),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          width: 10,
                          height: 10,
                          decoration: const BoxDecoration(color: AIHistoryApp._accentWarm, shape: BoxShape.circle),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          width: 10,
                          height: 10,
                          decoration: const BoxDecoration(color: AIHistoryApp._accentTertiary, shape: BoxShape.circle),
                        ),
                        const SizedBox(width: 14),
                        const Icon(Icons.terminal_rounded, color: Colors.white70, size: 18),
                        const SizedBox(width: 8),
                        const Text(
                          'FastAPI Server Console',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 14,
                            fontWeight: FontWeight.bold,
                            fontFamily: 'monospace',
                          ),
                        ),
                        const Spacer(),
                        IconButton(
                          icon: const Icon(Icons.copy_rounded, color: Colors.white60, size: 18),
                          tooltip: 'Copy all logs',
                          onPressed: () {
                            if (_consoleLogs.isNotEmpty) {
                              Clipboard.setData(ClipboardData(text: _consoleLogs.join('\n')));
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('Logs copied to clipboard'),
                                  backgroundColor: AIHistoryApp._accentTertiary,
                                  duration: Duration(seconds: 2),
                                ),
                              );
                            }
                          },
                        ),
                        IconButton(
                          icon: const Icon(Icons.delete_sweep_rounded, color: Colors.white60, size: 18),
                          tooltip: 'Clear console logs',
                          onPressed: () {
                            modalSetState(() {
                              setState(() {
                                _consoleLogs.clear();
                              });
                            });
                          },
                        ),
                        IconButton(
                          icon: const Icon(Icons.close_rounded, color: Colors.white60, size: 18),
                          onPressed: () => Navigator.pop(context),
                        ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: Container(
                      width: double.infinity,
                      color: const Color(0xFF07090E),
                      padding: const EdgeInsets.all(16),
                      child: _consoleLogs.isEmpty
                          ? const Center(
                              child: Text(
                                'No log records recorded yet.',
                                style: TextStyle(
                                  color: Colors.white24,
                                  fontFamily: 'monospace',
                                  fontSize: 13,
                                ),
                              ),
                            )
                          : SelectionArea(
                              child: ListView.builder(
                                controller: terminalScrollController,
                                itemCount: _consoleLogs.length,
                                itemBuilder: (context, index) {
                                  final line = _consoleLogs[index];
                                  Color textColor = Colors.white70;
                                  if (line.contains('[STDERR]') || 
                                      line.contains('ERROR') || 
                                      line.contains('CRITICAL') || 
                                      line.contains('Traceback') || 
                                      line.contains('Exception')) {
                                    textColor = AIHistoryApp._accentCoral;
                                  } else if (line.contains('[STDOUT]')) {
                                    textColor = const Color(0xFF94A3B8);
                                  } else if (line.contains('INFO') || 
                                             line.contains('Success') || 
                                             line.contains('200 OK') || 
                                             line.contains('respond')) {
                                    textColor = AIHistoryApp._accentTertiary;
                                  } else if (line.contains('WARNING') || line.contains('attempt')) {
                                    textColor = AIHistoryApp._accentWarm;
                                  }
                                  
                                  return Padding(
                                    padding: const EdgeInsets.only(bottom: 4.0),
                                    child: Text(
                                      line,
                                      style: TextStyle(
                                        color: textColor,
                                        fontFamily: 'monospace',
                                        fontSize: 12,
                                        height: 1.3,
                                      ),
                                    ),
                                  );
                                },
                              ),
                            ),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  @override
  void initState() {
    super.initState();
    _loadSessionsFromStorage();
    _checkAndStartBackend();
    _showInitialDialogIfNeeded();
  }

  Future<void> _showInitialDialogIfNeeded() async {
    try {
      final savedCreds = await _historyService.loadCredentials();
      if (savedCreds == null || savedCreds.url.isEmpty) {
        if (mounted) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            _showConnectDialog();
          });
        }
      }
    } catch (e) {
      debugPrint("Error evaluating startup credentials check: $e");
    }
  }

  Future<void> _loadSessionsFromStorage() async {
    final loaded = await _historyService.loadSessions();
    setState(() {
      _sessions = loaded;
      if (_sessions.isNotEmpty) {
        _currentSessionId = _sessions.first.id;
        _messages.clear();
        _messages.addAll(_sessions.first.messages);
      } else {
        _createNewSession();
      }
    });
  }

  void _createNewSession() {
    final newSessionId = DateTime.now().microsecondsSinceEpoch.toString();
    final newSession = ChatSession(
      id: newSessionId,
      title: 'New Chat',
      lastActive: DateTime.now(),
      messages: [],
    );
    setState(() {
      _sessions.insert(0, newSession);
      _currentSessionId = newSessionId;
      _messages.clear();
    });
    _saveSessionsToStorage();
  }

  Future<void> _saveSessionsToStorage() async {
    ChatSession? updatedSession;
    if (_currentSessionId != null) {
      final index = _sessions.indexWhere((s) => s.id == _currentSessionId);
      if (index != -1) {
        final current = _sessions[index];
        
        // Auto-generate a title based on the first user query if still default 'New Chat'
        String updatedTitle = current.title;
        if (updatedTitle == 'New Chat' && _messages.isNotEmpty) {
          final firstUserMsg = _messages.firstWhere(
            (m) => m.isUser, 
            orElse: () => ChatMessage(text: '', isUser: false)
          );
          if (firstUserMsg.text.isNotEmpty) {
            updatedTitle = firstUserMsg.text.length > 26 
                ? '${firstUserMsg.text.substring(0, 26)}...' 
                : firstUserMsg.text;
          }
        }

        updatedSession = ChatSession(
          id: current.id,
          title: updatedTitle,
          lastActive: DateTime.now(),
          messages: List.from(_messages),
        );
        _sessions[index] = updatedSession;
      }
    }
    
    // Re-sort sessions so most recently active is always on top
    _sessions.sort((a, b) => b.lastActive.compareTo(a.lastActive));
    await _historyService.saveSessions(_sessions);
    setState(() {});

    if (_isConnected && updatedSession != null) {
      _uploadSessionToSupabase(updatedSession);
    }
  }

  void _loadSession(String id) {
    final index = _sessions.indexWhere((s) => s.id == id);
    if (index != -1) {
      setState(() {
        _currentSessionId = id;
        _messages.clear();
        _messages.addAll(_sessions[index].messages);
      });
    }
  }

  void _deleteSession(String id) {
    setState(() {
      _sessions.removeWhere((s) => s.id == id);
      if (_currentSessionId == id) {
        if (_sessions.isNotEmpty) {
          _currentSessionId = _sessions.first.id;
          _messages.clear();
          _messages.addAll(_sessions.first.messages);
        } else {
          _createNewSession();
        }
      }
    });
    _saveSessionsToStorage();

    if (_isConnected) {
      _deleteSessionFromSupabase(id);
    }
  }

  void _addMessage(ChatMessage msg) {
    setState(() {
      _messages.add(msg);
    });
    _saveSessionsToStorage();
  }

  Future<void> _syncSessionsWithSupabase() async {
    if (!_isConnected) return;
    try {
      final response = await http.get(
        Uri.parse('$_baseUrl/chat-sessions'),
      );
      if (response.statusCode == 200) {
        final List<dynamic> jsonList = jsonDecode(response.body);
        final remoteSessions = jsonList.map((json) => ChatSession.fromJson(json as Map<String, dynamic>)).toList();
        
        final Map<String, ChatSession> localMap = {for (var s in _sessions) s.id: s};
        final Map<String, ChatSession> remoteMap = {for (var s in remoteSessions) s.id: s};
        
        final List<ChatSession> mergedSessions = [];
        final List<ChatSession> sessionsToUpload = [];
        
        for (var localSession in _sessions) {
          if (remoteMap.containsKey(localSession.id)) {
            final remoteSession = remoteMap[localSession.id]!;
            if (localSession.lastActive.isAfter(remoteSession.lastActive)) {
              mergedSessions.add(localSession);
              sessionsToUpload.add(localSession);
            } else {
              mergedSessions.add(remoteSession);
            }
          } else {
            mergedSessions.add(localSession);
            sessionsToUpload.add(localSession);
          }
        }
        
        for (var remoteSession in remoteSessions) {
          if (!localMap.containsKey(remoteSession.id)) {
            mergedSessions.add(remoteSession);
          }
        }
        
        mergedSessions.sort((a, b) => b.lastActive.compareTo(a.lastActive));
        
        setState(() {
          _sessions = mergedSessions;
          if (_sessions.isNotEmpty) {
            _currentSessionId = _sessions.first.id;
            _messages.clear();
            _messages.addAll(_sessions.first.messages);
          }
        });
        
        await _historyService.saveSessions(_sessions);
        
        for (var session in sessionsToUpload) {
          await _uploadSessionToSupabase(session);
        }
        
        debugPrint("Chat sync complete. Uploaded ${sessionsToUpload.length} sessions, merged total ${mergedSessions.length} sessions.");
      } else {
        debugPrint("Failed to fetch sessions from Supabase: ${response.statusCode}");
      }
    } catch (e) {
      debugPrint("Error syncing sessions with Supabase: $e");
    }
  }

  Future<void> _uploadSessionToSupabase(ChatSession session) async {
    if (!_isConnected) return;
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/chat-sessions'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(session.toJson()),
      );
      if (response.statusCode != 200) {
        debugPrint("Failed to upload session to Supabase: ${response.body}");
      }
    } catch (e) {
      debugPrint("Error uploading session to Supabase: $e");
    }
  }

  Future<void> _deleteSessionFromSupabase(String id) async {
    if (!_isConnected) return;
    try {
      final response = await http.delete(
        Uri.parse('$_baseUrl/chat-sessions/$id'),
      );
      if (response.statusCode != 200) {
        debugPrint("Failed to delete session on Supabase: ${response.body}");
      }
    } catch (e) {
      debugPrint("Error deleting session on Supabase: $e");
    }
  }

  @override
  void dispose() {
    _statusTimer?.cancel();
    _controller.dispose();
    _shutdownBackend();
    super.dispose();
  }

  // Getters for endpoint URLs
  String get _baseUrl {
    if (kIsWeb) return 'http://127.0.0.1:8000';
    if (Platform.isAndroid) return 'http://10.0.2.2:8000';
    return 'http://127.0.0.1:8000';
  }

  String get _apiUrl => '$_baseUrl/chat';
  String get _uploadUrl => '$_baseUrl/upload-and-process-csv';
  String get _connectDbUrl => '$_baseUrl/connect-db';
  String get _statusUrl => '$_baseUrl/status';
  String get _driftAnalysisUrl => '$_baseUrl/drift-analysis';
  String get _applyDriftUrl => '$_baseUrl/apply-drift';

  // Check backend status periodically when indexing
  void _startStatusPolling() {
    _statusTimer?.cancel();
    _statusTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
      if (!_isConnected) {
        _stopStatusPolling();
        return;
      }
      try {
        final response = await http.get(Uri.parse(_statusUrl));
        if (response.statusCode == 200) {
          final data = jsonDecode(response.body);
          final bool backendIsIndexing = data['is_indexing'] ?? false;
          final String backendMessage = data['indexing_message'] ?? "Ready";
          
          final bool wasIndexing = _isIndexing;
          
          if (backendIsIndexing != _isIndexing || backendMessage != _indexingMessage) {
            setState(() {
              _isIndexing = backendIsIndexing;
              _indexingMessage = backendMessage;
            });
            
            if (wasIndexing && !backendIsIndexing) {
              _addMessage(
                ChatMessage(
                  text: "🎉 **Ingestion & Indexing pipeline completed successfully!**\n\nAll logs have been fully vector-indexed and interest-classified. You can now execute semantic searches and generate chronological reports.",
                  isUser: false,
                ),
              );
              _stopStatusPolling();
            }
          } else if (!backendIsIndexing) {
            _stopStatusPolling();
          }
        }
      } catch (e) {
        debugPrint("Error during status polling: $e");
      }
    });
  }

  void _stopStatusPolling() {
    _statusTimer?.cancel();
    _statusTimer = null;
  }

  Future<void> _checkInitialStatus() async {
    try {
      final response = await http.get(Uri.parse(_statusUrl));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final bool backendIsIndexing = data['is_indexing'] ?? false;
        final String backendMessage = data['indexing_message'] ?? "Ready";
        setState(() {
          _isIndexing = backendIsIndexing;
          _indexingMessage = backendMessage;
        });
        if (backendIsIndexing) {
          _startStatusPolling();
        }
      }
    } catch (e) {
      debugPrint("Error checking initial status: $e");
    }
  }

  Future<void> _showConnectDialog() async {
    if (_isConnectingDb) {
      return showDialog(
        context: context,
        barrierDismissible: true,
        builder: (context) {
          return AlertDialog(
            backgroundColor: AIHistoryApp._bgCard,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
            title: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AIHistoryApp._accentPrimary.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const SizedBox(
                    width: 24,
                    height: 24,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.5,
                      valueColor: AlwaysStoppedAnimation<Color>(AIHistoryApp._accentPrimary),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                const Text(
                  'Auto-Connecting...',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 18),
                ),
              ],
            ),
            content: const Padding(
              padding: EdgeInsets.only(top: 8.0),
              child: Text(
                'The application is currently establishing connection and verifying schemas in the background. Please wait...',
                style: TextStyle(color: Colors.white70, fontSize: 14, height: 1.5),
              ),
            ),
            actions: [
              TextButton(
                style: TextButton.styleFrom(
                  foregroundColor: AIHistoryApp._accentPrimary,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                ),
                onPressed: () => Navigator.pop(context),
                child: const Text('OK', style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ],
          );
        },
      );
    }

    final savedCreds = await _historyService.loadCredentials();
    
    final TextEditingController dbUrlController = TextEditingController(text: savedCreds?.url ?? '');
    final TextEditingController dbPasswordController = TextEditingController(text: savedCreds?.password ?? '');
    final TextEditingController llmApiKeyController = TextEditingController(text: savedCreds?.llmApiKey ?? '');

    return showDialog(
      context: context,
      barrierDismissible: true,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AIHistoryApp._bgCard,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
          title: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AIHistoryApp._accentPrimary.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.security, color: AIHistoryApp._accentPrimary, size: 24),
              ),
              const SizedBox(width: 12),
              const Text(
                'Connect to Supabase',
                style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 18),
              ),
            ],
          ),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Provide database credentials to auto-migrate schemas & seed default categories.',
                  style: TextStyle(fontSize: 13, color: Colors.white60, height: 1.5),
                ),
                const SizedBox(height: 20),
                TextField(
                  controller: dbUrlController,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    labelText: 'Connection URL',
                    labelStyle: const TextStyle(color: Colors.white54),
                    hintText: 'postgresql://postgres.[REF]:[PASS]@[HOST]:[PORT]/postgres',
                    hintStyle: const TextStyle(color: Colors.white24),
                    filled: true,
                    fillColor: AIHistoryApp._bgDeep,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                    enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.08))),
                    focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AIHistoryApp._accentPrimary, width: 1.5)),
                  ),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: dbPasswordController,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    labelText: 'Raw Database Password',
                    labelStyle: const TextStyle(color: Colors.white54),
                    hintText: 'e.g. Fz5f9\$E2-#xbq!U',
                    hintStyle: const TextStyle(color: Colors.white24),
                    filled: true,
                    fillColor: AIHistoryApp._bgDeep,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                    enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.08))),
                    focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AIHistoryApp._accentPrimary, width: 1.5)),
                  ),
                  obscureText: true,
                ),
                const SizedBox(height: 22),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: AIHistoryApp._accentSecondary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Text(
                    '🧠  Provide your DeepSeek LLM API Key for taxonomy drift analysis & RAG reasoning.',
                    style: TextStyle(fontSize: 13, color: AIHistoryApp._accentSecondary, height: 1.5),
                  ),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: llmApiKeyController,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    labelText: 'DeepSeek API Key',
                    labelStyle: const TextStyle(color: Colors.white54),
                    hintText: 'sk-...',
                    hintStyle: const TextStyle(color: Colors.white24),
                    filled: true,
                    fillColor: AIHistoryApp._bgDeep,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                    enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.08))),
                    focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AIHistoryApp._accentSecondary, width: 1.5)),
                  ),
                  obscureText: true,
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              style: TextButton.styleFrom(
                foregroundColor: Colors.white60,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
              ),
              onPressed: () {
                Navigator.pop(context);
              },
              child: const Text('Skip / Browse History'),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: AIHistoryApp._accentPrimary,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
                elevation: 4,
              ),
              onPressed: () {
                Navigator.pop(context);
                _connectToDatabase(
                  dbUrlController.text.trim(),
                  dbPasswordController.text.trim(),
                  llmApiKeyController.text.trim(),
                );
              },
              child: const Text(
                'Connect & Initialize',
                style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 0.3),
              ),
            ),
          ],
        );
      },
    );
  }

  Future<void> _connectToDatabase(String url, String password, String llmApiKey) async {
    if (_isConnectingDb) {
      _addLog("[CONNECT] Prevented duplicate parallel database connection request.");
      return;
    }
    setState(() {
      _isConnectingDb = true;
      _isLoading = true;
    });
    _addMessage(ChatMessage(text: "⚙️ Connecting to services and verifying schemas...", isUser: false));

    String projectRef = '';
    String host = '';
    String port = '';

    if (url.isNotEmpty) {
      try {
        final refMatch = RegExp(r'postgres\.([^:]+)').firstMatch(url);
        if (refMatch != null) {
          projectRef = refMatch.group(1) ?? '';
        }

        final hostMatch = RegExp(r'@([^:\/]+)').firstMatch(url);
        if (hostMatch != null) {
          host = hostMatch.group(1) ?? host;
        }

        final portMatch = RegExp(r'@[^:]+:(\d+)\/').firstMatch(url);
        if (portMatch != null) {
          port = portMatch.group(1) ?? port;
        }
      } catch (e) {
        debugPrint('Error extracting details from URL: $e');
      }
    }

    try {
      final response = await http.post(
        Uri.parse(_connectDbUrl),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'db_project_ref': projectRef,
          'db_password': password,
          'db_host': host,
          'db_port': port,
          'llm_api_key': llmApiKey,
        }),
      );

      if (response.statusCode == 200) {
        // Save database credentials locally on successful connection
        await _historyService.saveCredentials(DbCredentials(
          url: url,
          password: password,
          llmApiKey: llmApiKey,
        ));

        setState(() {
          _isConnected = true;
          _serverStatus = "Connected";
        });
        _addMessage(
          ChatMessage(text: "✅ **Success:** Connected to Supabase!\n\nAll tables have been verified, schemas migrated, and interest taxonomy seeded. You are ready to upload history data and chat.", isUser: false),
        );
        _checkInitialStatus();
        _syncSessionsWithSupabase();
      } else {
        dynamic data;
        try {
          data = jsonDecode(response.body);
        } catch (_) {}
        final detail = (data is Map && data.containsKey('detail')) ? data['detail'] : response.statusCode;
        _addMessage(
          ChatMessage(
            text: "❌ Connection Failed: $detail. Please check your credentials or click 'Connect DB' in the toolbar to retry.",
            isUser: false,
          ),
        );
      }
    } catch (e) {
      _addMessage(
        ChatMessage(text: "Connection Error: $e. Please check if the local server is running and click 'Connect DB' in the toolbar to retry.", isUser: false),
      );
    } finally {
      setState(() {
        _isConnectingDb = false;
        _isLoading = false;
      });
    }
  }

  // Chrome Profiles state for automated ingestion
  List<String> _chromeProfiles = [];
  String? _selectedChromeProfile;
  bool _isLoadingProfiles = false;

  Future<void> _fetchChromeProfiles(void Function(void Function()) dialogSetState) async {
    dialogSetState(() {
      _isLoadingProfiles = true;
    });
    try {
      final response = await http.get(Uri.parse('http://localhost:8000/chrome-profiles'));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final List<dynamic> profilesList = data['profiles'] ?? [];
        dialogSetState(() {
          _chromeProfiles = profilesList.map((e) => e.toString()).toList();
          if (_chromeProfiles.contains('Profile 5')) {
            _selectedChromeProfile = 'Profile 5';
          } else if (_chromeProfiles.isNotEmpty) {
            _selectedChromeProfile = _chromeProfiles.first;
          } else {
            _selectedChromeProfile = null;
          }
        });
      }
    } catch (e) {
      debugPrint('Error fetching Chrome profiles: $e');
    } finally {
      dialogSetState(() {
        _isLoadingProfiles = false;
      });
    }
  }

  Future<void> _autoIngestChrome(String profile) async {
    if (!_isConnected || _isLoading || _isIndexing) {
      _addLog("[AUTO-INGEST] Blocked request because app is busy, indexing, or disconnected.");
      return;
    }
    setState(() {
      _isLoading = true;
    });
    _addMessage(ChatMessage(text: "⚡ Running 1-Click Auto-Ingest for Chrome profile '$profile'...", isUser: true));

    try {
      final response = await http.post(
        Uri.parse('http://localhost:8000/ingest-chrome-local'),
        body: {'profile': profile},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final bool isIndexingTriggered = data['indexing'] ?? false;

        _addMessage(
          ChatMessage(
            text: "✅ **Chrome Ingestion Complete!**\n\n- **Profile:** $profile\n- **Processed Rows:** ${data['rows_processed']}\n- **Stored Rows:** ${data['rows_stored']}\n\nAll Search browsing logs have been parsed and sent for indexing in the background.",
            isUser: false,
          ),
        );

        setState(() {
          if (isIndexingTriggered) {
            _isIndexing = true;
            _indexingMessage = "Generating BGE-small vector embeddings...";
          }
        });

        if (isIndexingTriggered) {
          _startStatusPolling();
        }
      } else {
        final data = jsonDecode(response.body);
        _addMessage(
          ChatMessage(
            text: "❌ Auto-Ingest Failed: ${data['detail'] ?? response.statusCode}",
            isUser: false,
          ),
        );
      }
    } catch (e) {
      _addMessage(ChatMessage(text: "Auto-Ingest Error: $e", isUser: false));
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _showUploadDialog() async {
    final TextEditingController apiKeyController = TextEditingController();
    bool profilesFetched = false;

    return showDialog(
      context: context,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, dialogSetState) {
            if (!profilesFetched && !_isLoadingProfiles) {
              profilesFetched = true;
              WidgetsBinding.instance.addPostFrameCallback((_) {
                _fetchChromeProfiles(dialogSetState);
              });
            }

            return AlertDialog(
              backgroundColor: AIHistoryApp._bgCard,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
              title: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: AIHistoryApp._accentPrimary.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(Icons.history_toggle_off_rounded, color: AIHistoryApp._accentPrimary, size: 24),
                  ),
                  const SizedBox(width: 12),
                  const Text(
                    'Ingest Browsing History',
                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 17),
                  ),
                ],
              ),
              content: SingleChildScrollView(
                child: SizedBox(
                  width: 480,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // --- GOOGLE TAKEOUT CARD ---
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: AIHistoryApp._bgDeep,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: AIHistoryApp._accentWarm.withValues(alpha: 0.2)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Icon(Icons.cloud_download_rounded, color: AIHistoryApp._accentWarm, size: 20),
                                const SizedBox(width: 8),
                                const Text(
                                  'Option A: Google Takeout Ingestion',
                                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13.5, color: Colors.white),
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            const Text(
                              'Supports Google Takeout CSV or native HTML (My Activity) formats. Requires a YouTube API Key to enrich channel & video metadata.',
                              style: TextStyle(fontSize: 11.5, color: Colors.white60, height: 1.4),
                            ),
                            const SizedBox(height: 12),
                            TextField(
                              controller: apiKeyController,
                              style: const TextStyle(color: Colors.white, fontSize: 12.5),
                              decoration: InputDecoration(
                                labelText: 'YouTube API Key (Optional)',
                                labelStyle: const TextStyle(color: Colors.white54, fontSize: 12),
                                hintText: 'AIza...',
                                hintStyle: const TextStyle(color: Colors.white24, fontSize: 12),
                                filled: true,
                                fillColor: AIHistoryApp._bgCard,
                                isDense: true,
                                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(10),
                                  borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.08)),
                                ),
                                focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(10),
                                  borderSide: const BorderSide(color: AIHistoryApp._accentWarm, width: 1.5),
                                ),
                              ),
                              obscureText: true,
                            ),
                            const SizedBox(height: 12),
                            SizedBox(
                              width: double.infinity,
                              child: ElevatedButton.icon(
                                icon: const Icon(Icons.file_open_outlined, size: 16),
                                label: const Text('Pick Takeout & Upload', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: AIHistoryApp._accentWarm,
                                  foregroundColor: Colors.black87,
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                                  padding: const EdgeInsets.symmetric(vertical: 12),
                                  elevation: 2,
                                ),
                                onPressed: () {
                                  Navigator.pop(context);
                                  _uploadCSV(apiKeyController.text.trim());
                                },
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),
                      
                      // --- CHROME BROWSER HISTORY CARD ---
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: AIHistoryApp._bgDeep,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: AIHistoryApp._accentSecondary.withValues(alpha: 0.2)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Icon(Icons.chrome_reader_mode_rounded, color: AIHistoryApp._accentSecondary, size: 20),
                                const SizedBox(width: 8),
                                const Text(
                                  'Option B: Chrome History Ingestion',
                                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13.5, color: Colors.white),
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            const Text(
                              'Ingest local history directly. Preserves browser page titles (critical to identify Grok Chat topics).',
                              style: TextStyle(fontSize: 11.5, color: Colors.white60, height: 1.4),
                            ),
                            const SizedBox(height: 12),
                            
                            // Auto-discovery Dropdown or Loader
                            if (_isLoadingProfiles)
                              const Row(
                                children: [
                                  SizedBox(
                                    width: 14,
                                    height: 14,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      valueColor: AlwaysStoppedAnimation<Color>(AIHistoryApp._accentSecondary),
                                    ),
                                  ),
                                  SizedBox(width: 8),
                                  Text(
                                    'Discovering local Chrome profiles...',
                                    style: TextStyle(fontSize: 11.5, color: Colors.white54),
                                  ),
                                ],
                              )
                            else if (_chromeProfiles.isEmpty)
                              const Text(
                                '⚠️ No local Chrome profiles auto-discovered.',
                                style: TextStyle(fontSize: 11.5, color: AIHistoryApp._accentCoral),
                              )
                            else ...[
                              const Text(
                                'Select Chrome Profile to Auto-Ingest:',
                                style: TextStyle(fontSize: 11.5, color: Colors.white70),
                              ),
                              const SizedBox(height: 6),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
                                decoration: BoxDecoration(
                                  color: AIHistoryApp._bgCard,
                                  borderRadius: BorderRadius.circular(10),
                                  border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
                                ),
                                child: DropdownButtonHideUnderline(
                                  child: DropdownButton<String>(
                                    value: _selectedChromeProfile,
                                    dropdownColor: AIHistoryApp._bgCard,
                                    isExpanded: true,
                                    icon: const Icon(Icons.arrow_drop_down, color: AIHistoryApp._accentSecondary),
                                    style: const TextStyle(color: Colors.white, fontSize: 13),
                                    items: _chromeProfiles.map((String profile) {
                                      return DropdownMenuItem<String>(
                                        value: profile,
                                        child: Text(profile),
                                      );
                                    }).toList(),
                                    onChanged: (String? newValue) {
                                      dialogSetState(() {
                                        _selectedChromeProfile = newValue;
                                      });
                                    },
                                  ),
                                ),
                              ),
                              const SizedBox(height: 12),
                              SizedBox(
                                width: double.infinity,
                                child: ElevatedButton.icon(
                                  icon: const Icon(Icons.bolt, size: 16),
                                  label: const Text('⚡ 1-Click Auto Ingest', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: AIHistoryApp._accentSecondary,
                                    foregroundColor: Colors.black87,
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                                    padding: const EdgeInsets.symmetric(vertical: 12),
                                    elevation: 2,
                                  ),
                                  onPressed: _selectedChromeProfile == null
                                      ? null
                                      : () {
                                          Navigator.pop(context);
                                          _autoIngestChrome(_selectedChromeProfile!);
                                        },
                                ),
                              ),
                            ],
                            
                            const SizedBox(height: 12),
                            const Divider(color: Colors.white10),
                            const SizedBox(height: 8),
                            
                            // Manual Ingestion Fallback Expandable
                            SizedBox(
                              width: double.infinity,
                              child: OutlinedButton.icon(
                                icon: const Icon(Icons.upload_file, size: 14),
                                label: const Text('Or: Upload CSV Manually', style: TextStyle(fontSize: 12)),
                                style: OutlinedButton.styleFrom(
                                  foregroundColor: Colors.white70,
                                  side: BorderSide(color: Colors.white.withValues(alpha: 0.1)),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                                  padding: const EdgeInsets.symmetric(vertical: 10),
                                ),
                                onPressed: () {
                                  Navigator.pop(context);
                                  _uploadCSV("");
                                },
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Cancel', style: TextStyle(color: Colors.white38)),
                ),
              ],
            );
          },
        );
      },
    );
  }

  Future<void> _uploadCSV(String apiKey) async {
    if (!_isConnected || _isLoading || _isIndexing) {
      _addLog("[UPLOAD] Blocked file picker launch because app is busy, indexing, or disconnected.");
      return;
    }
    try {
      FilePickerResult? result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['csv', 'html'],
      );

      if (result == null) return;

      setState(() {
        _isLoading = true;
      });
      _addMessage(ChatMessage(text: "📤 Preparing and uploading digital history file...", isUser: true));

      final file = result.files.single;
      var request = http.MultipartRequest('POST', Uri.parse(_uploadUrl));

      request.fields['api_key'] = apiKey;

      if (kIsWeb) {
        if (file.bytes != null) {
          request.files.add(
            http.MultipartFile.fromBytes(
              'file',
              file.bytes!,
              filename: file.name,
            ),
          );
        }
      } else {
        if (file.path != null) {
          request.files.add(
            await http.MultipartFile.fromPath(
              'file',
              file.path!,
              filename: file.name,
            ),
          );
        }
      }

      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final bool isIndexingTriggered = data['indexing'] ?? false;
        
        _addMessage(
          ChatMessage(
            text: "✅ **CSV Uploaded & Enriched!**\n\n- **Service:** ${data['service_type'].toString().toUpperCase()}\n- **Processed Rows:** ${data['rows_processed']}\n- **Stored Rows:** ${data['rows_stored']}\n\n${data['message']}",
            isUser: false,
          ),
        );
        
        setState(() {
          if (isIndexingTriggered) {
            _isIndexing = true;
            _indexingMessage = "Generating BGE-small vector embeddings...";
          }
        });
        
        if (isIndexingTriggered) {
          _startStatusPolling();
        }
      } else {
        final data = jsonDecode(response.body);
        _addMessage(
          ChatMessage(
            text: "❌ Upload Failed: ${data['detail'] ?? response.statusCode}",
            isUser: false,
          ),
        );
      }
    } catch (e) {
      _addMessage(ChatMessage(text: "Upload Error: $e", isUser: false));
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _sendMessage(String text) async {
    if (text.trim().isEmpty) return;
    if (!_isConnected || _isLoading || _isIndexing) {
      _addLog("[CHAT] Blocked message send because app is busy, indexing, or disconnected.");
      return;
    }

    _addMessage(ChatMessage(text: text, isUser: true));
    setState(() {
      _isLoading = true;
    });

    _controller.clear();

    try {
      final response = await http.post(
        Uri.parse(_apiUrl),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'query': text}),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _addMessage(ChatMessage(text: data['response'], isUser: false, steps: data['steps']));
      } else {
        _addMessage(
          ChatMessage(
            text: "Server Error: ${response.statusCode}",
            isUser: false,
          ),
        );
      }
    } catch (e) {
      _addMessage(
        ChatMessage(
          text: "Connection Failed. Is the Python server running?",
          isUser: false,
        ),
      );
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _showDriftDialog() async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: AIHistoryApp._bgCard,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          content: const Row(
            children: [
              CircularProgressIndicator(valueColor: AlwaysStoppedAnimation<Color>(AIHistoryApp._accentSecondary)),
              SizedBox(width: 20),
              Text("Analyzing taxonomy drift & anomalies...", style: TextStyle(color: Colors.white70)),
            ],
          ),
        );
      },
    );

    try {
      final response = await http.get(Uri.parse(_driftAnalysisUrl));
      if (!mounted) return;
      Navigator.pop(context); // Pop loading dialog

      if (response.statusCode != 200) {
        throw Exception("Failed to analyze drift: ${response.statusCode}");
      }

      final data = jsonDecode(response.body);
      final bool driftFound = data['drift_found'] ?? false;
      final List<dynamic> suggestedCats = data['suggested_categories'] ?? [];
      final List<dynamic> sampleLogs = data['drifted_logs_sample'] ?? [];
      final String backendMsg = data['message'] ?? "";

      if (!driftFound || suggestedCats.isEmpty) {
        if (!mounted) return;
        showDialog(
          context: context,
          builder: (BuildContext context) {
            return AlertDialog(
              backgroundColor: AIHistoryApp._bgCard,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
              title: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: AIHistoryApp._accentTertiary.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(Icons.check_circle_rounded, color: AIHistoryApp._accentTertiary, size: 22),
                  ),
                  const SizedBox(width: 12),
                  const Text("Taxonomy Intact", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                ],
              ),
              content: Text(
                backendMsg.isNotEmpty ? backendMsg : "No taxonomy drift found! Your current interests cover your activity well.",
                style: const TextStyle(color: Colors.white60, height: 1.5),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text("Awesome", style: TextStyle(color: AIHistoryApp._accentTertiary, fontWeight: FontWeight.w600)),
                ),
              ],
            );
          },
        );
        return;
      }

      List<String> selectedCategories = List<String>.from(suggestedCats);

      if (!mounted) return;
      showDialog(
        context: context,
        builder: (BuildContext context) {
          return StatefulBuilder(
            builder: (BuildContext context, StateSetter setModalState) {
              return AlertDialog(
                backgroundColor: AIHistoryApp._bgCard,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
                title: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: AIHistoryApp._accentSecondary.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Icon(Icons.psychology, color: AIHistoryApp._accentSecondary, size: 24),
                    ),
                    const SizedBox(width: 12),
                    const Text(
                      "Taxonomy Drift Detected",
                      style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
                content: SizedBox(
                  width: 500,
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Text(
                          "We found digital logs that don't match your existing interests. The DeepSeek LLM analyzed these anomalies and suggested the following new interest categories:",
                          style: TextStyle(color: Colors.white60, fontSize: 13, height: 1.5),
                        ),
                        const SizedBox(height: 16),
                        
                        // Suggested Categories Checklist
                        Container(
                          decoration: BoxDecoration(
                            color: AIHistoryApp._bgDeep,
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(color: AIHistoryApp._accentSecondary.withValues(alpha: 0.12)),
                          ),
                          child: Column(
                            children: suggestedCats.map((cat) {
                              final String category = cat.toString();
                              final bool isSelected = selectedCategories.contains(category);
                              return CheckboxListTile(
                                activeColor: AIHistoryApp._accentSecondary,
                                checkColor: AIHistoryApp._bgDeep,
                                title: Text(category, style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500)),
                                value: isSelected,
                                onChanged: (bool? checked) {
                                  setModalState(() {
                                    if (checked == true) {
                                      selectedCategories.add(category);
                                    } else {
                                      selectedCategories.remove(category);
                                    }
                                  });
                                },
                              );
                            }).toList(),
                          ),
                        ),
                        const SizedBox(height: 20),
                        
                        // Sample Drifted Logs
                        if (sampleLogs.isNotEmpty) ...[
                          const Text(
                            "SAMPLE OF UNMATCHED LOGS",
                            style: TextStyle(color: AIHistoryApp._accentSecondary, fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 1.2),
                          ),
                          const SizedBox(height: 10),
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: AIHistoryApp._bgDeep,
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(color: Colors.white.withValues(alpha: 0.05)),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: sampleLogs.map((log) {
                                final text = log['text'] ?? '';
                                final confidence = (log['confidence'] as num?)?.toDouble() ?? 0.0;
                                final source = log['source'] ?? 'log';
                                return Padding(
                                  padding: const EdgeInsets.only(bottom: 10.0),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          Icon(
                                            source == 'youtube' ? Icons.play_circle_filled : Icons.search_rounded,
                                            size: 15,
                                            color: source == 'youtube' ? AIHistoryApp._accentCoral : AIHistoryApp._accentWarm,
                                          ),
                                          const SizedBox(width: 8),
                                          Expanded(
                                            child: Text(
                                              text,
                                              style: const TextStyle(color: Colors.white70, fontSize: 12.5),
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 3),
                                      Text(
                                        "Confidence: ${(confidence * 100).toStringAsFixed(1)}%",
                                        style: TextStyle(color: Colors.white.withValues(alpha: 0.3), fontSize: 10),
                                      ),
                                    ],
                                  ),
                                );
                              }).toList(),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text("Cancel", style: TextStyle(color: Colors.white38)),
                  ),
                  ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AIHistoryApp._accentSecondary,
                      foregroundColor: AIHistoryApp._bgDeep,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                      padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
                      elevation: 4,
                    ),
                    onPressed: selectedCategories.isEmpty
                        ? null
                        : () {
                            Navigator.pop(context);
                            _applyDrift(selectedCategories);
                          },
                    child: const Text("Apply New Interests", style: TextStyle(fontWeight: FontWeight.bold)),
                  ),
                ],
              );
            },
          );
        },
      );
    } catch (e) {
      if (!mounted) return;
      Navigator.pop(context); // Pop loading
      showDialog(
        context: context,
        builder: (BuildContext context) {
          return AlertDialog(
            backgroundColor: AIHistoryApp._bgCard,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
            title: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AIHistoryApp._accentCoral.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.error_rounded, color: AIHistoryApp._accentCoral, size: 22),
                ),
                const SizedBox(width: 12),
                const Text("Drift Analysis Failed", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
              ],
            ),
            content: Text("Error: $e", style: const TextStyle(color: Colors.white60, height: 1.4)),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text("Close", style: TextStyle(color: AIHistoryApp._accentCoral, fontWeight: FontWeight.w600)),
              ),
            ],
          );
        },
      );
    }
  }

  Future<void> _applyDrift(List<String> categories) async {
    if (!_isConnected || _isLoading || _isIndexing) {
      _addLog("[DRIFT] Blocked apply drift request because app is busy, indexing, or disconnected.");
      return;
    }
    setState(() {
      _isLoading = true;
    });
    _addMessage(
      ChatMessage(
        text: "Applying selected categories: ${categories.join(', ')}...",
        isUser: true,
      ),
    );

    try {
      final response = await http.post(
        Uri.parse(_applyDriftUrl),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'categories': categories}),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        setState(() {
          _isIndexing = true;
          _indexingMessage = "Re-classifying logs to new interests...";
        });
        _addMessage(
          ChatMessage(
            text: "✅ Categories applied successfully!\n\n${data['message']}\n\nRe-classification is now running asynchronously in the background. The agent will notify you once completed.",
            isUser: false,
          ),
        );
        _startStatusPolling();
      } else {
        final data = jsonDecode(response.body);
        _addMessage(
          ChatMessage(
            text: "❌ Apply Drift Failed: ${data['detail'] ?? response.statusCode}",
            isUser: false,
          ),
        );
      }
    } catch (e) {
      _addMessage(ChatMessage(text: "Apply Drift Error: $e", isUser: false));
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Widget _buildServerStatusBadge() {
    Color badgeColor;
    IconData badgeIcon;
    bool shouldGlow = false;

    if (_isConnected) {
      badgeColor = AIHistoryApp._accentTertiary; // Emerald success
      badgeIcon = Icons.check_circle_rounded;
    } else if (_isServerStarting) {
      badgeColor = AIHistoryApp._accentWarm; // Amber starting
      badgeIcon = Icons.sync_rounded;
      shouldGlow = true;
    } else {
      badgeColor = AIHistoryApp._accentCoral; // Coral error
      badgeIcon = Icons.error_outline_rounded;
    }

    Widget badge = Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: badgeColor.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: badgeColor.withValues(alpha: 0.3), width: 1),
        boxShadow: shouldGlow
            ? [
                BoxShadow(
                  color: badgeColor.withValues(alpha: 0.2),
                  blurRadius: 8,
                  spreadRadius: 1,
                )
              ]
            : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_isServerStarting)
            const SizedBox(
              width: 12,
              height: 12,
              child: CircularProgressIndicator(
                strokeWidth: 2.0,
                valueColor: AlwaysStoppedAnimation<Color>(AIHistoryApp._accentWarm),
              ),
            )
          else
            Icon(badgeIcon, color: badgeColor, size: 14),
          const SizedBox(width: 6),
          Text(
            _serverStatus,
            style: TextStyle(
              color: badgeColor,
              fontSize: 12,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
    return badge;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('My AI Data Analyst', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, letterSpacing: 0.3)),
        backgroundColor: AIHistoryApp._bgSurface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        actions: [
          _buildServerStatusBadge(),
          if (!_isConnected)
            TextButton.icon(
              onPressed: _isServerStarting || _isConnectingDb ? null : _showConnectDialog,
              icon: _isConnectingDb
                  ? const SizedBox(
                      width: 14,
                      height: 14,
                      child: CircularProgressIndicator(
                        strokeWidth: 1.5,
                        valueColor: AlwaysStoppedAnimation<Color>(AIHistoryApp._accentPrimary),
                      ),
                    )
                  : const Icon(Icons.link_rounded, size: 16),
              label: Text(_isConnectingDb ? "Connecting..." : "Connect DB"),
              style: TextButton.styleFrom(
                foregroundColor: AIHistoryApp._accentPrimary,
              ),
            ),
          if (_isConnected) ...[
            IconButton(
              icon: const Icon(Icons.upload_file_rounded, color: AIHistoryApp._accentWarm),
              tooltip: 'Ingest Browsing History',
              onPressed: _isIndexing || _isLoading || _isServerStarting || _isConnectingDb ? null : _showUploadDialog,
            ),
            IconButton(
              icon: const Icon(Icons.psychology_rounded, color: AIHistoryApp._accentSecondary),
              tooltip: 'Analyze Taxonomy Drift',
              onPressed: _isIndexing || _isLoading || _isServerStarting || _isConnectingDb ? null : _showDriftDialog,
            ),
          ],
          IconButton(
            icon: const Icon(Icons.terminal_rounded, color: Colors.white70),
            tooltip: 'View Server Logs',
            onPressed: _showTerminalLogs,
          ),
          const SizedBox(width: 8),
        ],
      ),
      drawer: Drawer(
        backgroundColor: AIHistoryApp._bgCard,
        elevation: 16,

        child: Column(
          children: [
            // Drawer Header
            Container(
              padding: const EdgeInsets.only(top: 60.0, left: 16.0, right: 16.0, bottom: 20.0),
              decoration: const BoxDecoration(
                color: AIHistoryApp._bgSurface,
                border: Border(bottom: BorderSide(color: Colors.white10, width: 0.5)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.history_edu_rounded, color: AIHistoryApp._accentPrimary, size: 28),
                      SizedBox(width: 10),
                      Text(
                        'Chat Sessions',
                        style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                          letterSpacing: 0.3,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  
                  // "+ New Chat" Gradient Button
                  InkWell(
                    onTap: () {
                      Navigator.pop(context); // Close drawer
                      _createNewSession();
                    },
                    borderRadius: BorderRadius.circular(14),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 14.0, horizontal: 16.0),
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          colors: [AIHistoryApp._accentPrimary, Color(0xFF9333EA)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        borderRadius: BorderRadius.circular(14),
                        boxShadow: [
                          BoxShadow(
                            color: AIHistoryApp._accentPrimary.withValues(alpha: 0.25),
                            blurRadius: 8,
                            offset: const Offset(0, 3),
                          ),
                        ],
                      ),
                      child: const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.add_rounded, color: Colors.white, size: 20),
                          SizedBox(width: 8),
                          Text(
                            'New Chat',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                              fontSize: 14.5,
                              letterSpacing: 0.3,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),

            // Scrollable List of Historical Sessions
            Expanded(
              child: _sessions.isEmpty
                  ? const Center(
                      child: Text(
                        'No history found',
                        style: TextStyle(color: Colors.white30, fontSize: 13),
                      ),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
                      itemCount: _sessions.length,
                      itemBuilder: (context, index) {
                        final session = _sessions[index];
                        final bool isActive = session.id == _currentSessionId;
                        
                        return Container(
                          margin: const EdgeInsets.only(bottom: 6.0),
                          decoration: BoxDecoration(
                            color: isActive 
                                ? AIHistoryApp._accentPrimary.withValues(alpha: 0.12)
                                : Colors.transparent,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: isActive 
                                  ? AIHistoryApp._accentPrimary.withValues(alpha: 0.25)
                                  : Colors.transparent,
                              width: 1.0,
                            ),
                          ),
                          child: ListTile(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 12.0),
                            dense: true,
                            leading: Icon(
                              Icons.chat_bubble_outline_rounded,
                              size: 18,
                              color: isActive 
                                  ? AIHistoryApp._accentSecondary 
                                  : Colors.white38,
                            ),
                            title: Text(
                              session.title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: isActive ? Colors.white : Colors.white70,
                                fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
                                fontSize: 13.5,
                              ),
                            ),
                            trailing: IconButton(
                              icon: const Icon(Icons.delete_outline_rounded, size: 18, color: AIHistoryApp._accentCoral),
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(),
                              onPressed: () {
                                _deleteSession(session.id);
                              },
                            ),
                            onTap: () {
                              Navigator.pop(context); // Close drawer
                              _loadSession(session.id);
                            },
                          ),
                        );
                      },
                    ),
            ),
            
            // Drawer Footer
            Container(
              padding: const EdgeInsets.all(16.0),
              decoration: const BoxDecoration(
                color: AIHistoryApp._bgDeep,
                border: Border(top: BorderSide(color: Colors.white10, width: 0.5)),
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.memory_rounded, size: 14, color: Colors.white38),
                  SizedBox(width: 6),
                  Text(
                    'Local Document Database',
                    style: TextStyle(color: Colors.white38, fontSize: 11, fontWeight: FontWeight.w500),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          // Backend Startup / Error / Database offline status banner
          if (!_isConnected)
            Builder(
              builder: (context) {
                final bool isBackendOnline = _serverStatus.startsWith("Connected") || _serverStatus == "Database Offline";
                
                Color bannerBgStart;
                Color bannerBgEnd;
                IconData bannerIcon;
                Color bannerIconColor;
                String bannerText;
                Widget? bannerAction;
                
                if (_isServerStarting) {
                  bannerBgStart = const Color(0xFF1E3A8A); // Blue
                  bannerBgEnd = const Color(0xFF0F172A);
                  bannerIcon = Icons.info_outline_rounded;
                  bannerIconColor = AIHistoryApp._accentWarm;
                  bannerText = 'Locating environment and launching FastAPI backend API server...';
                  bannerAction = TextButton.icon(
                    onPressed: _showTerminalLogs,
                    icon: const Icon(Icons.terminal_rounded, size: 14),
                    label: const Text('Open Console', style: TextStyle(fontSize: 12)),
                    style: TextButton.styleFrom(
                      foregroundColor: AIHistoryApp._accentWarm,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    ),
                  );
                } else if (isBackendOnline) {
                  bannerBgStart = const Color(0xFF78350F); // Amber / Brown-orange
                  bannerBgEnd = const Color(0xFF0F172A);
                  bannerIcon = Icons.cloud_off_rounded;
                  bannerIconColor = AIHistoryApp._accentWarm;
                  bannerText = 'FastAPI server is running, but database is disconnected. Connect to initialize agent.';
                  bannerAction = TextButton.icon(
                    onPressed: _showConnectDialog,
                    icon: const Icon(Icons.link_rounded, size: 14),
                    label: const Text('Connect Database', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                    style: TextButton.styleFrom(
                      foregroundColor: AIHistoryApp._accentWarm,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    ),
                  );
                } else {
                  bannerBgStart = const Color(0xFF7F1D1D); // Red
                  bannerBgEnd = const Color(0xFF0F172A);
                  bannerIcon = Icons.warning_amber_rounded;
                  bannerIconColor = AIHistoryApp._accentCoral;
                  bannerText = 'Backend offline or failed to start automatically. Please check logs for details.';
                  bannerAction = TextButton.icon(
                    onPressed: _showTerminalLogs,
                    icon: const Icon(Icons.terminal_rounded, size: 14),
                    label: const Text('Open Console', style: TextStyle(fontSize: 12)),
                    style: TextButton.styleFrom(
                      foregroundColor: AIHistoryApp._accentCoral,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    ),
                  );
                }
                
                return Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 12.0),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [bannerBgStart, bannerBgEnd],
                      begin: Alignment.centerLeft,
                      end: Alignment.centerRight,
                    ),
                    border: const Border(
                      bottom: BorderSide(color: Colors.white10, width: 0.5),
                    ),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        bannerIcon,
                        color: bannerIconColor,
                        size: 20,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          bannerText,
                          style: const TextStyle(color: Colors.white70, fontSize: 13),
                        ),
                      ),
                      if (bannerAction != null) bannerAction,
                    ],
                  ),
                );
              }
            ),

          // Indexing Status Banner
          if (_isIndexing)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 12.0),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF0E4D92), Color(0xFF1A1040), Color(0xFF0A0E1A)],
                  stops: [0.0, 0.6, 1.0],
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                ),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF0E4D92).withValues(alpha: 0.25),
                    blurRadius: 12,
                    offset: const Offset(0, 3),
                  )
                ],
              ),
              child: Row(
                children: [
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: AIHistoryApp._accentSecondary.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Center(
                      child: SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(AIHistoryApp._accentSecondary),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Background Indexing Active',
                          style: TextStyle(
                            color: AIHistoryApp._accentSecondary,
                            fontWeight: FontWeight.bold,
                            fontSize: 13,
                            letterSpacing: 0.3,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          _indexingMessage,
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.6),
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

          // Chat List
          Expanded(
            child: SelectionArea(
              child: ListView.builder(
                padding: const EdgeInsets.all(16.0),
                itemCount: _messages.length,
                itemBuilder: (context, index) {
                  final msg = _messages[index];
                  return Align(
                    alignment: msg.isUser
                        ? Alignment.centerRight
                        : Alignment.centerLeft,
                    child: Container(
                      margin: const EdgeInsets.only(bottom: 8.0),
                      padding: const EdgeInsets.all(14.0),
                      constraints: BoxConstraints(
                        maxWidth: MediaQuery.of(context).size.width * 0.75,
                      ),
                      decoration: BoxDecoration(
                        gradient: msg.isUser
                            ? const LinearGradient(
                                colors: [Color(0xFFD97706), Color(0xFFEA580C)],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              )
                            : const LinearGradient(
                                colors: [Color(0xFF141829), Color(0xFF1A1F36)],
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                              ),
                        borderRadius: BorderRadius.only(
                          topLeft: const Radius.circular(18.0),
                          topRight: const Radius.circular(18.0),
                          bottomLeft: msg.isUser ? const Radius.circular(18.0) : const Radius.circular(4.0),
                          bottomRight: msg.isUser ? const Radius.circular(4.0) : const Radius.circular(18.0),
                        ),
                        border: msg.isUser
                            ? null
                            : Border.all(color: Colors.white.withValues(alpha: 0.06), width: 1.0),
                        boxShadow: [
                          BoxShadow(
                            color: msg.isUser
                                ? const Color(0xFFD97706).withValues(alpha: 0.2)
                                : Colors.black.withValues(alpha: 0.15),
                            blurRadius: 8.0,
                            offset: const Offset(0, 3),
                          ),
                        ],
                      ),
                      child: msg.isUser
                          ? Text(
                              msg.text,
                              style: const TextStyle(fontSize: 15.0, color: Colors.white, fontWeight: FontWeight.w500),
                            )
                          : Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                MarkdownBody(
                                  data: msg.text,
                                  styleSheet: MarkdownStyleSheet(
                                    p: const TextStyle(fontSize: 15.0, color: Color(0xFFCBD5E1), height: 1.5),
                                    listBullet: const TextStyle(fontSize: 15.0, color: Color(0xFFCBD5E1)),
                                    h1: const TextStyle(fontSize: 22.0, fontWeight: FontWeight.bold, color: Colors.white),
                                    h2: const TextStyle(fontSize: 18.0, fontWeight: FontWeight.bold, color: Color(0xFFE2E8F0)),
                                    h3: const TextStyle(fontSize: 16.0, fontWeight: FontWeight.bold, color: Color(0xFFE2E8F0)),
                                    strong: const TextStyle(fontWeight: FontWeight.bold, color: AIHistoryApp._accentSecondary),
                                    code: const TextStyle(
                                      fontSize: 13.5,
                                      color: AIHistoryApp._accentCoral,
                                      backgroundColor: Color(0xFF0D1017),
                                    ),
                                    codeblockDecoration: BoxDecoration(
                                      color: const Color(0xFF0D1017),
                                      borderRadius: BorderRadius.circular(10),
                                      border: Border.all(color: Colors.white.withValues(alpha: 0.04)),
                                    ),
                                  ),
                                ),
                                if (msg.steps != null && msg.steps!.isNotEmpty)
                                  AgentTraceWidget(steps: msg.steps!),
                              ],
                            ),
                    ),
                  );
                },
              ),
            ),
          ),

          // Loading Indicator
          if (_isLoading)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 14.0),
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AIHistoryApp._bgCard,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const SizedBox(
                  width: 24, height: 24,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.5,
                    valueColor: AlwaysStoppedAnimation<Color>(AIHistoryApp._accentSecondary),
                  ),
                ),
              ),
            ),

          // Quick Actions
          if (_isConnected && !_isLoading && !_isIndexing)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
              child: Row(
                children: [
                  ActionChip(
                    avatar: const Icon(Icons.analytics_rounded, size: 16, color: AIHistoryApp._accentPrimary),
                    label: const Text('Generate Chronological Report', style: TextStyle(color: Colors.white70, fontSize: 13)),
                    backgroundColor: AIHistoryApp._bgCard,
                    side: BorderSide(color: AIHistoryApp._accentPrimary.withValues(alpha: 0.2)),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    onPressed: () {
                      _sendMessage("Give me a detailed chronological report of how my interests have evolved over the years based on my digital history.");
                    },
                  ),
                  const SizedBox(width: 8),
                  ActionChip(
                    avatar: const Icon(Icons.psychology_rounded, size: 16, color: AIHistoryApp._accentSecondary),
                    label: const Text('Analyze Taxonomy Drift', style: TextStyle(color: Colors.white70, fontSize: 13)),
                    backgroundColor: AIHistoryApp._bgCard,
                    side: BorderSide(color: AIHistoryApp._accentSecondary.withValues(alpha: 0.2)),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    onPressed: _showDriftDialog,
                  ),
                ],
              ),
            ),

          // Input Box
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: 10.0,
              vertical: 12.0,
            ),
            decoration: BoxDecoration(
              color: AIHistoryApp._bgSurface,
              border: Border(top: BorderSide(color: Colors.white.withValues(alpha: 0.04))),
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    enabled: _isConnected && !_isIndexing,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      hintText: !_isConnected
                          ? 'Please connect to Supabase first...'
                          : _isIndexing
                              ? 'Indexing and classifications in progress...'
                              : 'Ask about your digital history...',
                      hintStyle: const TextStyle(color: Colors.white24),
                      filled: true,
                      fillColor: AIHistoryApp._bgDeep,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(28.0),
                        borderSide: BorderSide.none,
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(28.0),
                        borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.06)),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(28.0),
                        borderSide: const BorderSide(color: AIHistoryApp._accentPrimary, width: 1.5),
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 20.0,
                        vertical: 14.0,
                      ),
                    ),
                    onSubmitted: _isConnected && !_isIndexing ? _sendMessage : null,
                  ),
                ),
                const SizedBox(width: 10.0),
                Container(
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [AIHistoryApp._accentPrimary, Color(0xFF9333EA)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: IconButton(
                    icon: const Icon(Icons.send_rounded, color: Colors.white, size: 20),
                    onPressed: (_isConnected && !_isIndexing) ? () => _sendMessage(_controller.text) : null,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class AgentTraceWidget extends StatefulWidget {
  final List<dynamic> steps;
  const AgentTraceWidget({super.key, required this.steps});

  @override
  State<AgentTraceWidget> createState() => _AgentTraceWidgetState();
}

class _AgentTraceWidgetState extends State<AgentTraceWidget> {
  bool _isExpanded = false;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 12.0),
      decoration: BoxDecoration(
        color: const Color(0xFF0F1222),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: const Color(0xFF1E2648),
          width: 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header Toggle button
          InkWell(
            onTap: () {
              setState(() {
                _isExpanded = !_isExpanded;
              });
            },
            borderRadius: BorderRadius.circular(12),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 12.0),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(
                      color: const Color(0xFF38BDF8).withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(
                      Icons.psychology_rounded,
                      color: Color(0xFF38BDF8),
                      size: 18,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'View Agent Execution Trace (${widget.steps.length} steps)',
                      style: const TextStyle(
                        color: Color(0xFF38BDF8),
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                        letterSpacing: 0.2,
                      ),
                    ),
                  ),
                  Icon(
                    _isExpanded 
                        ? Icons.keyboard_arrow_up_rounded 
                        : Icons.keyboard_arrow_down_rounded,
                    color: const Color(0xFF38BDF8),
                    size: 20,
                  ),
                ],
              ),
            ),
          ),
          
          // Collapsible Steps content
          if (_isExpanded) ...[
            const Divider(color: Color(0xFF1E2648), height: 1.0),
            Padding(
              padding: const EdgeInsets.all(14.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: List.generate(widget.steps.length, (index) {
                  final step = widget.steps[index] as Map<String, dynamic>;
                  final int stepNum = index + 1;
                  return _buildStepItem(stepNum, step);
                }),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildStepItem(int stepNum, Map<String, dynamic> step) {
    final String thought = step['thought'] ?? '';
    final List<dynamic> actions = step['actions'] ?? [];
    final List<dynamic> observations = step['observations'] ?? [];

    return Container(
      margin: const EdgeInsets.only(bottom: 16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Step Header
          Row(
            children: [
              Container(
                width: 22,
                height: 22,
                decoration: const BoxDecoration(
                  color: Color(0xFF38BDF8),
                  shape: BoxShape.circle,
                ),
                child: Center(
                  child: Text(
                    '$stepNum',
                    style: const TextStyle(
                      color: Color(0xFF0A0E1A),
                      fontWeight: FontWeight.bold,
                      fontSize: 12,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              const Text(
                'Agent Reason & Action',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                ),
              ),
            ],
          ),
          
          // Thought Card
          if (thought.isNotEmpty)
            Container(
              margin: const EdgeInsets.only(left: 30.0, top: 6.0),
              padding: const EdgeInsets.all(10.0),
              width: double.infinity,
              decoration: BoxDecoration(
                color: const Color(0xFF161B30),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.white.withValues(alpha: 0.03)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Thought',
                    style: TextStyle(
                      color: Colors.white38,
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1.0,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    thought,
                    style: const TextStyle(
                      color: Color(0xFF94A3B8),
                      fontSize: 12.5,
                      fontStyle: FontStyle.italic,
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),

          // Actions
          if (actions.isNotEmpty)
            ...actions.map((action) {
              final Map<dynamic, dynamic> actionMap = action as Map<dynamic, dynamic>;
              final String toolName = actionMap['name'] ?? 'Unknown Tool';
              final Map<dynamic, dynamic>? toolArgs = actionMap['args'] as Map<dynamic, dynamic>?;
              final formattedCall = _formatToolCall(toolName, toolArgs);

              return Container(
                margin: const EdgeInsets.only(left: 30.0, top: 8.0),
                padding: const EdgeInsets.all(10.0),
                width: double.infinity,
                decoration: BoxDecoration(
                  color: const Color(0xFF0F172A),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFF334155).withValues(alpha: 0.3)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.play_arrow_rounded, color: Color(0xFF34D399), size: 14),
                        const SizedBox(width: 4),
                        Text(
                          'Execute Tool: $toolName',
                          style: const TextStyle(
                            color: Color(0xFF34D399),
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF090D16),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: SelectableText(
                        formattedCall,
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 11,
                          color: Color(0xFFCBD5E1),
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }),

          // Observations (Outputs)
          if (observations.isNotEmpty)
            ...observations.map((obs) {
              return Container(
                margin: const EdgeInsets.only(left: 30.0, top: 8.0),
                padding: const EdgeInsets.all(10.0),
                width: double.infinity,
                decoration: BoxDecoration(
                  color: const Color(0xFF0D1017),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.white.withValues(alpha: 0.04)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.remove_red_eye_outlined, color: Color(0xFFF59E0B), size: 14),
                        const SizedBox(width: 4),
                        const Text(
                          'Observation (Tool Output)',
                          style: TextStyle(
                            color: Color(0xFFF59E0B),
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Container(
                      width: double.infinity,
                      constraints: const BoxConstraints(maxHeight: 120.0),
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF07090E),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: SingleChildScrollView(
                        scrollDirection: Axis.vertical,
                        child: SelectableText(
                          obs.toString(),
                          style: const TextStyle(
                            fontFamily: 'monospace',
                            fontSize: 11,
                            color: Color(0xFFCBD5E1),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }

  String _formatToolCall(String name, Map<dynamic, dynamic>? args) {
    if (args == null || args.isEmpty) {
      return '$name()';
    }
    try {
      final String formattedArgs = const JsonEncoder.withIndent('  ').convert(args);
      return '$name(\n$formattedArgs\n)';
    } catch (e) {
      return '$name($args)';
    }
  }
}
