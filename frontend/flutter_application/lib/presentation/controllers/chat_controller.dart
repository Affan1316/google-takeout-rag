import 'dart:async';
import 'package:flutter/foundation.dart';
import '../../domain/entities/chat_message.dart';
import '../../domain/entities/chat_session.dart';
import '../../domain/entities/db_credentials.dart';
import '../../domain/usecases/chat_sessions_usecases.dart';
import '../../domain/usecases/db_credentials_usecases.dart';
import '../../domain/usecases/backend_process_usecases.dart';
import '../../domain/usecases/backend_api_usecases.dart';

class ChatController extends ChangeNotifier {
  final ChatSessionsUsecases chatSessionsUsecases;
  final DbCredentialsUsecases dbCredentialsUsecases;
  final BackendProcessUsecases backendProcessUsecases;
  final BackendApiUsecases backendApiUsecases;

  ChatController({
    required this.chatSessionsUsecases,
    required this.dbCredentialsUsecases,
    required this.backendProcessUsecases,
    required this.backendApiUsecases,
  });

  // State Variables
  final List<ChatMessage> _messages = [];
  List<ChatMessage> get messages => _messages;

  bool _isLoading = false;
  bool get isLoading => _isLoading;

  bool _isConnected = false;
  bool get isConnected => _isConnected;

  bool _isIndexing = false;
  bool get isIndexing => _isIndexing;

  String _indexingMessage = "Ready";
  String get indexingMessage => _indexingMessage;

  bool _isConnectingDb = false;
  bool get isConnectingDb => _isConnectingDb;

  List<ChatSession> _sessions = [];
  List<ChatSession> get sessions => _sessions;

  String? _currentSessionId;
  String? get currentSessionId => _currentSessionId;

  final List<String> _consoleLogs = [];
  List<String> get consoleLogs => _consoleLogs;

  String _serverStatus = "Initializing...";
  String get serverStatus => _serverStatus;

  bool _isServerStarting = false;
  bool get isServerStarting => _isServerStarting;

  List<String> _chromeProfiles = [];
  List<String> get chromeProfiles => _chromeProfiles;

  String? _selectedChromeProfile;
  String? get selectedChromeProfile => _selectedChromeProfile;

  bool _isLoadingProfiles = false;
  bool get isLoadingProfiles => _isLoadingProfiles;

  Timer? _statusTimer;

  // Initialization
  Future<void> initialize() async {
    await _loadSessionsFromStorage();
    await checkAndStartBackend();
    await _showInitialDialogIfNeeded();
  }

  void selectChromeProfile(String? profile) {
    _selectedChromeProfile = profile;
    notifyListeners();
  }

  void _addLog(String line) {
    final timestamp = DateTime.now().toLocal().toString().substring(11, 19);
    final formattedLine = '[$timestamp] $line';
    debugPrint(formattedLine);
    if (_consoleLogs.length >= 500) {
      _consoleLogs.removeAt(0);
    }
    _consoleLogs.add(formattedLine);
    notifyListeners();
  }

  Future<void> _loadSessionsFromStorage() async {
    final loaded = await chatSessionsUsecases.loadSessions();
    _sessions = loaded;
    if (_sessions.isNotEmpty) {
      _currentSessionId = _sessions.first.id;
      _messages.clear();
      _messages.addAll(_sessions.first.messages);
    } else {
      createNewSession();
    }
    notifyListeners();
  }

  Future<void> _showInitialDialogIfNeeded() async {
    try {
      final savedCreds = await dbCredentialsUsecases.loadCredentials();
      if (savedCreds == null || savedCreds.url.isEmpty) {
        // Handled in UI via callback or controller flags
      }
    } catch (e) {
      debugPrint("Error evaluating startup credentials check: $e");
    }
  }

  Future<bool> hasSavedCredentials() async {
    final savedCreds = await dbCredentialsUsecases.loadCredentials();
    return savedCreds != null && savedCreds.url.isNotEmpty;
  }

  Future<DbCredentials?> getSavedCredentials() async {
    return dbCredentialsUsecases.loadCredentials();
  }

  // Session Operations
  void createNewSession() {
    final newSessionId = DateTime.now().microsecondsSinceEpoch.toString();
    final newSession = ChatSession(
      id: newSessionId,
      title: 'New Chat',
      lastActive: DateTime.now(),
      messages: [],
    );
    _sessions.insert(0, newSession);
    _currentSessionId = newSessionId;
    _messages.clear();
    _saveSessionsToStorage();
    notifyListeners();
  }

  Future<void> _saveSessionsToStorage() async {
    ChatSession? updatedSession;
    if (_currentSessionId != null) {
      final index = _sessions.indexWhere((s) => s.id == _currentSessionId);
      if (index != -1) {
        final current = _sessions[index];

        // Auto-generate a title based on the first user query
        String updatedTitle = current.title;
        if (updatedTitle == 'New Chat' && _messages.isNotEmpty) {
          final firstUserMsg = _messages.firstWhere(
            (m) => m.isUser,
            orElse: () => ChatMessage(text: '', isUser: false),
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

    _sessions.sort((a, b) => b.lastActive.compareTo(a.lastActive));
    await chatSessionsUsecases.saveSessions(_sessions);
    notifyListeners();

    if (_isConnected && updatedSession != null) {
      _uploadSessionToSupabase(updatedSession);
    }
  }

  void loadSession(String id) {
    final index = _sessions.indexWhere((s) => s.id == id);
    if (index != -1) {
      _currentSessionId = id;
      _messages.clear();
      _messages.addAll(_sessions[index].messages);
      notifyListeners();
    }
  }

  void deleteSession(String id) {
    _sessions.removeWhere((s) => s.id == id);
    if (_currentSessionId == id) {
      if (_sessions.isNotEmpty) {
        _currentSessionId = _sessions.first.id;
        _messages.clear();
        _messages.addAll(_sessions.first.messages);
      } else {
        createNewSession();
      }
    }
    _saveSessionsToStorage();
    notifyListeners();

    if (_isConnected) {
      _deleteSessionFromSupabase(id);
    }
  }

  void addMessage(ChatMessage msg) {
    _messages.add(msg);
    _saveSessionsToStorage();
    notifyListeners();
  }

  // Backend Process Operations
  Future<void> checkAndStartBackend() async {
    if (kIsWeb) {
      _serverStatus = "Unsupported on Web";
      notifyListeners();
      return;
    }

    _addLog("[AUTO-START] Checking if backend API server is already online...");
    try {
      final isOnline = await backendProcessUsecases.checkBackendOnline();
      if (isOnline) {
        _addLog("[AUTO-START] Backend is already running manually.");
        final statusMap = await backendProcessUsecases.fetchBackendStatus();
        final bool dbConnected = statusMap['database_connected'] ?? false;
        final bool backendIsIndexing = statusMap['is_indexing'] ?? false;
        final String backendMessage = statusMap['indexing_message'] ?? "Ready";

        _isConnected = dbConnected;
        _isIndexing = backendIsIndexing;
        _indexingMessage = backendMessage;
        _serverStatus = dbConnected ? "Connected (External)" : "Database Offline";
        notifyListeners();

        _checkInitialStatus();

        if (!dbConnected) {
          _autoConnectDatabase();
        }
        return;
      }
    } catch (_) {}

    _isServerStarting = true;
    _serverStatus = "Starting...";
    notifyListeners();

    _addLog("[AUTO-START] Backend not found on port 8000. Initiating auto-start sequence...");

    try {
      await backendProcessUsecases.startBackendProcess(
        onLog: (line) {
          _addLog(line);
        },
        onExit: (code) {
          _addLog("[PROCESS] Backend exited with code $code");
          if (_isConnected || _isServerStarting) {
            _isConnected = false;
            _isServerStarting = false;
            _serverStatus = "Exited ($code)";
            notifyListeners();
          }
        },
      );
    } catch (e) {
      _isServerStarting = false;
      _serverStatus = "Error Spawning";
      notifyListeners();
      return;
    }

    _addLog("[AUTO-START] Polling backend health endpoint...");
    bool serverCameOnline = false;
    Map<String, dynamic>? onlineStatus;

    const int maxAttempts = 75;
    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
      await Future.delayed(const Duration(milliseconds: 800));
      try {
        final isOnline = await backendProcessUsecases.checkBackendOnline();
        if (isOnline) {
          _addLog("[AUTO-START] Backend server successfully responded on port 8000!");
          serverCameOnline = true;
          onlineStatus = await backendProcessUsecases.fetchBackendStatus();
          break;
        }
      } catch (_) {
        _addLog("[AUTO-START] Health check attempt $attempt/$maxAttempts: waiting for server...");
      }
    }

    if (serverCameOnline && onlineStatus != null) {
      final bool dbConnected = onlineStatus['database_connected'] ?? false;
      final bool backendIsIndexing = onlineStatus['is_indexing'] ?? false;
      final String backendMessage = onlineStatus['indexing_message'] ?? "Ready";

      _isConnected = dbConnected;
      _isServerStarting = false;
      _isIndexing = backendIsIndexing;
      _indexingMessage = backendMessage;
      _serverStatus = dbConnected ? "Connected" : "Database Offline";
      notifyListeners();

      _checkInitialStatus();

      if (!dbConnected) {
        _autoConnectDatabase();
      }
    } else {
      _addLog("[AUTO-START] ERROR: Backend server failed to respond within timeout.");
      _isServerStarting = false;
      _serverStatus = "Start Failed";
      notifyListeners();
    }
  }

  Future<void> _autoConnectDatabase() async {
    try {
      final creds = await dbCredentialsUsecases.loadCredentials();
      if (creds != null && creds.url.isNotEmpty) {
        _addLog("[AUTO-CONNECT] Local credentials found. Autoconnecting in background...");
        await connectToDatabase(creds.url, creds.password, creds.llmApiKey);
      } else {
        _addLog("[AUTO-CONNECT] No saved database credentials found.");
      }
    } catch (e) {
      _addLog("[AUTO-CONNECT] Exception during background auto-connect: $e");
    }
  }

  void shutdownBackend() {
    backendProcessUsecases.shutdownBackendProcess();
    _stopStatusPolling();
  }

  // Database Connection
  Future<void> connectToDatabase(String url, String password, String llmApiKey) async {
    if (_isConnectingDb) {
      _addLog("[CONNECT] Prevented duplicate parallel database connection request.");
      return;
    }
    _isConnectingDb = true;
    _isLoading = true;
    notifyListeners();

    addMessage(ChatMessage(
        text: "⚙️ Connecting to services and verifying schemas...", isUser: false));

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
      final isConnectedSuccess = await dbCredentialsUsecases.connectDatabase(
        projectRef: projectRef,
        password: password,
        host: host,
        port: port,
        llmApiKey: llmApiKey,
      );

      if (isConnectedSuccess) {
        await dbCredentialsUsecases.saveCredentials(DbCredentials(
          url: url,
          password: password,
          llmApiKey: llmApiKey,
        ));

        _isConnected = true;
        _serverStatus = "Connected";
        notifyListeners();

        addMessage(ChatMessage(
            text:
                "✅ **Success:** Connected to Supabase!\n\nAll tables have been verified, schemas migrated, and interest taxonomy seeded. You are ready to upload history data and chat.",
            isUser: false));

        _checkInitialStatus();
        _syncSessionsWithSupabase();
      } else {
        addMessage(ChatMessage(
          text:
              "❌ Connection Failed. Please check your credentials or click 'Connect DB' in the toolbar to retry.",
          isUser: false,
        ));
      }
    } catch (e) {
      addMessage(ChatMessage(
          text:
              "Connection Error: $e. Please check if the local server is running and click 'Connect DB' in the toolbar to retry.",
          isUser: false));
    } finally {
      _isConnectingDb = false;
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> disconnectFromDatabase() async {
    _isLoading = true;
    notifyListeners();

    try {
      final success = await backendApiUsecases.disconnectDatabase();
      if (success) {
        _addLog("[DISCONNECT] Disconnected backend from database.");
      } else {
        _addLog("[DISCONNECT] Backend disconnect endpoint returned failure.");
      }
    } catch (e) {
      _addLog("[DISCONNECT] Error notifying backend: $e");
    }

    try {
      await dbCredentialsUsecases.deleteCredentials();
      _addLog("[DISCONNECT] Deleted saved credentials from local storage.");
    } catch (e) {
      _addLog("[DISCONNECT] Error deleting local credentials: $e");
    }

    _isConnected = false;
    _isIndexing = false;
    _serverStatus = "Database Offline";

    addMessage(ChatMessage(
      text: "🔌 **Disconnected:** Database connection closed and cached credentials have been deleted. You can connect again by clicking 'Connect DB' in the toolbar.",
      isUser: false,
    ));

    _isLoading = false;
    notifyListeners();
  }

  // Supabase Synchronizations
  Future<void> _syncSessionsWithSupabase() async {
    if (!_isConnected) return;
    try {
      final remoteSessions = await chatSessionsUsecases.fetchSessionsFromSupabase();
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

      _sessions = mergedSessions;
      if (_sessions.isNotEmpty) {
        _currentSessionId = _sessions.first.id;
        _messages.clear();
        _messages.addAll(_sessions.first.messages);
      }
      notifyListeners();

      await chatSessionsUsecases.saveSessions(_sessions);

      for (var session in sessionsToUpload) {
        await _uploadSessionToSupabase(session);
      }

      _addLog(
          "Chat sync complete. Uploaded ${sessionsToUpload.length} sessions, merged total ${mergedSessions.length} sessions.");
    } catch (e) {
      _addLog("Error syncing sessions with Supabase: $e");
    }
  }

  Future<void> _uploadSessionToSupabase(ChatSession session) async {
    if (!_isConnected) return;
    try {
      await chatSessionsUsecases.uploadSessionToSupabase(session);
    } catch (e) {
      debugPrint("Error uploading session to Supabase: $e");
    }
  }

  Future<void> _deleteSessionFromSupabase(String id) async {
    if (!_isConnected) return;
    try {
      await chatSessionsUsecases.deleteSessionFromSupabase(id);
    } catch (e) {
      debugPrint("Error deleting session on Supabase: $e");
    }
  }

  // Status Polling for Vector Indexing
  void _startStatusPolling() {
    _statusTimer?.cancel();
    _statusTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
      if (!_isConnected) {
        _stopStatusPolling();
        return;
      }
      try {
        final data = await backendProcessUsecases.fetchBackendStatus();
        final bool backendIsIndexing = data['is_indexing'] ?? false;
        final String backendMessage = data['indexing_message'] ?? "Ready";

        final bool wasIndexing = _isIndexing;

        if (backendIsIndexing != _isIndexing || backendMessage != _indexingMessage) {
          _isIndexing = backendIsIndexing;
          _indexingMessage = backendMessage;
          notifyListeners();

          if (wasIndexing && !backendIsIndexing) {
            addMessage(
              ChatMessage(
                text:
                    "🎉 **Ingestion & Indexing pipeline completed successfully!**\n\nAll logs have been fully vector-indexed and interest-classified. You can now execute semantic searches and generate chronological reports.",
                isUser: false,
              ),
            );
            _stopStatusPolling();
          }
        } else if (!backendIsIndexing) {
          _stopStatusPolling();
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
      final data = await backendProcessUsecases.fetchBackendStatus();
      final bool backendIsIndexing = data['is_indexing'] ?? false;
      final String backendMessage = data['indexing_message'] ?? "Ready";
      _isIndexing = backendIsIndexing;
      _indexingMessage = backendMessage;
      notifyListeners();

      if (backendIsIndexing) {
        _startStatusPolling();
      }
    } catch (e) {
      debugPrint("Error checking initial status: $e");
    }
  }

  // Ingestion Operations
  Future<void> fetchChromeProfiles() async {
    _isLoadingProfiles = true;
    notifyListeners();
    try {
      final list = await backendApiUsecases.fetchChromeProfiles();
      _chromeProfiles = list;
      if (_chromeProfiles.contains('Profile 5')) {
        _selectedChromeProfile = 'Profile 5';
      } else if (_chromeProfiles.isNotEmpty) {
        _selectedChromeProfile = _chromeProfiles.first;
      } else {
        _selectedChromeProfile = null;
      }
    } catch (e) {
      debugPrint('Error fetching Chrome profiles: $e');
    } finally {
      _isLoadingProfiles = false;
      notifyListeners();
    }
  }

  Future<void> autoIngestChrome(String profile) async {
    if (!_isConnected || _isLoading || _isIndexing) {
      _addLog("[AUTO-INGEST] Blocked request because app is busy, indexing, or disconnected.");
      return;
    }
    _isLoading = true;
    notifyListeners();

    addMessage(ChatMessage(
        text: "⚡ Running 1-Click Auto-Ingest for Chrome profile '$profile'...",
        isUser: true));

    try {
      final data = await backendApiUsecases.autoIngestChrome(profile);
      final bool isIndexingTriggered = data['indexing'] ?? false;

      addMessage(
        ChatMessage(
          text:
              "✅ **Chrome Ingestion Complete!**\n\n- **Profile:** $profile\n- **Processed Rows:** ${data['rows_processed']}\n- **Stored Rows:** ${data['rows_stored']}\n\nAll Search browsing logs have been parsed and sent for indexing in the background.",
          isUser: false,
        ),
      );

      if (isIndexingTriggered) {
        _isIndexing = true;
        _indexingMessage = "Generating BGE-small vector embeddings...";
        notifyListeners();
        _startStatusPolling();
      }
    } catch (e) {
      addMessage(ChatMessage(text: "Auto-Ingest Error: $e", isUser: false));
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> uploadCSV(String apiKey, List<int> bytes, String filename, String? path) async {
    if (!_isConnected || _isLoading || _isIndexing) {
      _addLog(
          "[UPLOAD] Blocked file picker launch because app is busy, indexing, or disconnected.");
      return;
    }
    _isLoading = true;
    notifyListeners();

    addMessage(ChatMessage(
        text: "📤 Preparing and uploading digital history file...", isUser: true));

    try {
      final data = await backendApiUsecases.uploadCSV(
        apiKey: apiKey,
        bytes: bytes,
        filename: filename,
        path: path,
      );
      final bool isIndexingTriggered = data['indexing'] ?? false;

      addMessage(
        ChatMessage(
          text:
              "✅ **CSV Uploaded & Enriched!**\n\n- **Service:** ${data['service_type'].toString().toUpperCase()}\n- **Processed Rows:** ${data['rows_processed']}\n- **Stored Rows:** ${data['rows_stored']}\n\n${data['message']}",
          isUser: false,
        ),
      );

      if (isIndexingTriggered) {
        _isIndexing = true;
        _indexingMessage = "Generating BGE-small vector embeddings...";
        notifyListeners();
        _startStatusPolling();
      }
    } catch (e) {
      addMessage(ChatMessage(text: "Upload Error: $e", isUser: false));
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  // Chat Operations
  Future<void> sendMessage(String text) async {
    if (text.trim().isEmpty) return;
    if (!_isConnected || _isLoading || _isIndexing) {
      _addLog(
          "[CHAT] Blocked message send because app is busy, indexing, or disconnected.");
      return;
    }

    addMessage(ChatMessage(text: text, isUser: true));
    _isLoading = true;
    notifyListeners();

    try {
      final data = await backendApiUsecases.sendChatMessage(text);
      addMessage(ChatMessage(
          text: data['response'], isUser: false, steps: data['steps']));
    } catch (e) {
      addMessage(
        ChatMessage(
          text: "Connection Failed. Is the Python server running?",
          isUser: false,
        ),
      );
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  // Drift Analysis & Migrations
  Future<Map<String, dynamic>> runDriftAnalysis() async {
    return backendApiUsecases.analyzeTaxonomyDrift();
  }

  Future<void> applyDrift(List<String> categories) async {
    if (!_isConnected || _isLoading || _isIndexing) {
      _addLog(
          "[DRIFT] Blocked apply drift request because app is busy, indexing, or disconnected.");
      return;
    }
    _isLoading = true;
    notifyListeners();

    addMessage(
      ChatMessage(
        text: "Applying selected categories: ${categories.join(', ')}...",
        isUser: true,
      ),
    );

    try {
      final data = await backendApiUsecases.applyTaxonomyDrift(categories);
      _isIndexing = true;
      _indexingMessage = "Re-classifying logs to new interests...";
      notifyListeners();

      addMessage(
        ChatMessage(
          text:
              "✅ Categories applied successfully!\n\n${data['message']}\n\nRe-classification is now running asynchronously in the background. The agent will notify you once completed.",
          isUser: false,
        ),
      );
      _startStatusPolling();
    } catch (e) {
      addMessage(ChatMessage(text: "Apply Drift Error: $e", isUser: false));
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void clearLogs() {
    _consoleLogs.clear();
    notifyListeners();
  }

  @override
  void dispose() {
    _statusTimer?.cancel();
    shutdownBackend();
    super.dispose();
  }
}
