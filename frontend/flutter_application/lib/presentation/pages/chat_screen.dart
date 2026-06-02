import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import 'package:flutter_markdown/flutter_markdown.dart';
import '../../core/theme/app_theme.dart';
import '../controllers/chat_controller.dart';
import '../widgets/agent_trace_widget.dart';
import '../widgets/server_status_badge.dart';
import '../widgets/status_banners.dart';
import '../widgets/dialogs/connect_dialog.dart';
import '../widgets/dialogs/upload_dialog.dart';
import '../widgets/dialogs/drift_dialog.dart';

class ChatScreen extends StatefulWidget {
  final ChatController controller;

  const ChatScreen({
    super.key,
    required this.controller,
  });

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _textController = TextEditingController();

  @override
  void initState() {
    super.initState();
    // Hook up listener to trigger rebuilds on state changes
    widget.controller.addListener(_onStateChange);
  }

  void _onStateChange() {
    if (mounted) {
      setState(() {});
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onStateChange);
    _textController.dispose();
    super.dispose();
  }

  void _sendMessage(String text) {
    if (text.trim().isNotEmpty) {
      widget.controller.sendMessage(text);
      _textController.clear();
    }
  }

  void _showConnectDialog() {
    showDialog(
      context: context,
      barrierDismissible: true,
      builder: (context) => ConnectDialog(controller: widget.controller),
    );
  }

  void _showUploadDialog() {
    showDialog(
      context: context,
      builder: (context) => UploadDialog(controller: widget.controller),
    );
  }

  void _showDriftDialog() {
    showDialog(
      context: context,
      builder: (context) => DriftDialog(controller: widget.controller),
    );
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
        return ListenableBuilder(
          listenable: widget.controller,
          builder: (BuildContext context, _) {
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
                color: AppTheme.bgDeep,
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
                      color: AppTheme.bgSurface,
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
                          decoration: const BoxDecoration(color: AppTheme.accentCoral, shape: BoxShape.circle),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          width: 10,
                          height: 10,
                          decoration: const BoxDecoration(color: AppTheme.accentWarm, shape: BoxShape.circle),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          width: 10,
                          height: 10,
                          decoration: const BoxDecoration(color: AppTheme.accentTertiary, shape: BoxShape.circle),
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
                            if (widget.controller.consoleLogs.isNotEmpty) {
                              Clipboard.setData(ClipboardData(text: widget.controller.consoleLogs.join('\n')));
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('Logs copied to clipboard'),
                                  backgroundColor: AppTheme.accentTertiary,
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
                            widget.controller.clearLogs();
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
                      child: widget.controller.consoleLogs.isEmpty
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
                                itemCount: widget.controller.consoleLogs.length,
                                itemBuilder: (context, index) {
                                  final line = widget.controller.consoleLogs[index];
                                  Color textColor = Colors.white70;
                                  if (line.contains('[STDERR]') ||
                                      line.contains('ERROR') ||
                                      line.contains('CRITICAL') ||
                                      line.contains('Traceback') ||
                                      line.contains('Exception')) {
                                    textColor = AppTheme.accentCoral;
                                  } else if (line.contains('[STDOUT]')) {
                                    textColor = const Color(0xFF94A3B8);
                                  } else if (line.contains('INFO') ||
                                      line.contains('Success') ||
                                      line.contains('200 OK') ||
                                      line.contains('respond')) {
                                    textColor = AppTheme.accentTertiary;
                                  } else if (line.contains('WARNING') || line.contains('attempt')) {
                                    textColor = AppTheme.accentWarm;
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
  Widget build(BuildContext context) {
    final controller = widget.controller;

    return Scaffold(
      appBar: AppBar(
        title: const Text('My AI Data Analyst',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, letterSpacing: 0.3)),
        backgroundColor: AppTheme.bgSurface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        actions: [
          ServerStatusBadge(
            isConnected: controller.isConnected,
            isServerStarting: controller.isServerStarting,
            serverStatus: controller.serverStatus,
          ),
          if (!controller.isConnected)
            TextButton.icon(
              onPressed: controller.isServerStarting || controller.isConnectingDb
                  ? null
                  : _showConnectDialog,
              icon: controller.isConnectingDb
                  ? const SizedBox(
                      width: 14,
                      height: 14,
                      child: CircularProgressIndicator(
                        strokeWidth: 1.5,
                        valueColor: AlwaysStoppedAnimation<Color>(AppTheme.accentPrimary),
                      ),
                    )
                  : const Icon(Icons.link_rounded, size: 16),
              label: Text(controller.isConnectingDb ? "Connecting..." : "Connect DB"),
              style: TextButton.styleFrom(
                foregroundColor: AppTheme.accentPrimary,
              ),
            ),
          if (controller.isConnected) ...[
            IconButton(
              icon: const Icon(Icons.upload_file_rounded, color: AppTheme.accentWarm),
              tooltip: 'Ingest Browsing History',
              onPressed: controller.isIndexing ||
                      controller.isLoading ||
                      controller.isServerStarting ||
                      controller.isConnectingDb
                  ? null
                  : _showUploadDialog,
            ),
            IconButton(
              icon: const Icon(Icons.psychology_rounded, color: AppTheme.accentSecondary),
              tooltip: 'Analyze Taxonomy Drift',
              onPressed: controller.isIndexing ||
                      controller.isLoading ||
                      controller.isServerStarting ||
                      controller.isConnectingDb
                  ? null
                  : _showDriftDialog,
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
        backgroundColor: AppTheme.bgCard,
        elevation: 16,
        child: Column(
          children: [
            // Drawer Header
            Container(
              padding: const EdgeInsets.only(top: 60.0, left: 16.0, right: 16.0, bottom: 20.0),
              decoration: const BoxDecoration(
                color: AppTheme.bgSurface,
                border: Border(bottom: BorderSide(color: Colors.white10, width: 0.5)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.history_edu_rounded, color: AppTheme.accentPrimary, size: 28),
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
                      controller.createNewSession();
                    },
                    borderRadius: BorderRadius.circular(14),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 14.0, horizontal: 16.0),
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          colors: [AppTheme.accentPrimary, Color(0xFF9333EA)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        borderRadius: BorderRadius.circular(14),
                        boxShadow: [
                          BoxShadow(
                            color: AppTheme.accentPrimary.withValues(alpha: 0.25),
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
              child: controller.sessions.isEmpty
                  ? const Center(
                      child: Text(
                        'No history found',
                        style: TextStyle(color: Colors.white30, fontSize: 13),
                      ),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
                      itemCount: controller.sessions.length,
                      itemBuilder: (context, index) {
                        final session = controller.sessions[index];
                        final bool isActive = session.id == controller.currentSessionId;

                        return Container(
                          margin: const EdgeInsets.only(bottom: 6.0),
                          decoration: BoxDecoration(
                            color: isActive
                                ? AppTheme.accentPrimary.withValues(alpha: 0.12)
                                : Colors.transparent,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: isActive
                                  ? AppTheme.accentPrimary.withValues(alpha: 0.25)
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
                              color: isActive ? AppTheme.accentSecondary : Colors.white38,
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
                              icon: const Icon(Icons.delete_outline_rounded,
                                  size: 18, color: AppTheme.accentCoral),
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(),
                              onPressed: () {
                                controller.deleteSession(session.id);
                              },
                            ),
                            onTap: () {
                              Navigator.pop(context); // Close drawer
                              controller.loadSession(session.id);
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
                color: AppTheme.bgDeep,
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
          if (!controller.isConnected)
            ConnectionStatusBanner(
              isServerStarting: controller.isServerStarting,
              serverStatus: controller.serverStatus,
              onShowConsole: _showTerminalLogs,
              onConnectDatabase: _showConnectDialog,
            ),

          // Indexing Status Banner
          if (controller.isIndexing)
            IndexingStatusBanner(indexingMessage: controller.indexingMessage),

          // Chat List
          Expanded(
            child: SelectionArea(
              child: ListView.builder(
                padding: const EdgeInsets.all(16.0),
                itemCount: controller.messages.length,
                itemBuilder: (context, index) {
                  final msg = controller.messages[index];
                  return Align(
                    alignment: msg.isUser ? Alignment.centerRight : Alignment.centerLeft,
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
                              style: const TextStyle(
                                  fontSize: 15.0, color: Colors.white, fontWeight: FontWeight.w500),
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
                                    h1: const TextStyle(
                                        fontSize: 22.0, fontWeight: FontWeight.bold, color: Colors.white),
                                    h2: const TextStyle(
                                        fontSize: 18.0, fontWeight: FontWeight.bold, color: Color(0xFFE2E8F0)),
                                    h3: const TextStyle(
                                        fontSize: 16.0, fontWeight: FontWeight.bold, color: Color(0xFFE2E8F0)),
                                    strong: const TextStyle(
                                        fontWeight: FontWeight.bold, color: AppTheme.accentSecondary),
                                    code: const TextStyle(
                                      fontSize: 13.5,
                                      color: AppTheme.accentCoral,
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
          if (controller.isLoading)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 14.0),
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppTheme.bgCard,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.5,
                    valueColor: AlwaysStoppedAnimation<Color>(AppTheme.accentSecondary),
                  ),
                ),
              ),
            ),

          // Quick Actions
          if (controller.isConnected && !controller.isLoading && !controller.isIndexing)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
              child: Row(
                children: [
                  ActionChip(
                    avatar: const Icon(Icons.analytics_rounded, size: 16, color: AppTheme.accentPrimary),
                    label: const Text('Generate Chronological Report',
                        style: TextStyle(color: Colors.white70, fontSize: 13)),
                    backgroundColor: AppTheme.bgCard,
                    side: BorderSide(color: AppTheme.accentPrimary.withValues(alpha: 0.2)),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    onPressed: () {
                      _sendMessage(
                          "Give me a detailed chronological report of how my interests have evolved over the years based on my digital history.");
                    },
                  ),
                  const SizedBox(width: 8),
                  ActionChip(
                    avatar:
                        const Icon(Icons.psychology_rounded, size: 16, color: AppTheme.accentSecondary),
                    label: const Text('Analyze Taxonomy Drift',
                        style: TextStyle(color: Colors.white70, fontSize: 13)),
                    backgroundColor: AppTheme.bgCard,
                    side: BorderSide(color: AppTheme.accentSecondary.withValues(alpha: 0.2)),
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
              color: AppTheme.bgSurface,
              border: Border(top: BorderSide(color: Colors.white.withValues(alpha: 0.04))),
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _textController,
                    enabled: controller.isConnected && !controller.isIndexing,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      hintText: !controller.isConnected
                          ? 'Please connect to Supabase first...'
                          : controller.isIndexing
                              ? 'Indexing and classifications in progress...'
                              : 'Ask about your digital history...',
                      hintStyle: const TextStyle(color: Colors.white24),
                      filled: true,
                      fillColor: AppTheme.bgDeep,
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
                        borderSide: const BorderSide(color: AppTheme.accentPrimary, width: 1.5),
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 20.0,
                        vertical: 14.0,
                      ),
                    ),
                    onSubmitted: controller.isConnected && !controller.isIndexing ? _sendMessage : null,
                  ),
                ),
                const SizedBox(width: 10.0),
                Container(
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [AppTheme.accentPrimary, Color(0xFF9333EA)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: IconButton(
                    icon: const Icon(Icons.send_rounded, color: Colors.white, size: 20),
                    onPressed: (controller.isConnected && !controller.isIndexing)
                        ? () => _sendMessage(_textController.text)
                        : null,
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
