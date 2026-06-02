import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';

class ConnectionStatusBanner extends StatelessWidget {
  final bool isServerStarting;
  final String serverStatus;
  final VoidCallback onShowConsole;
  final VoidCallback onConnectDatabase;

  const ConnectionStatusBanner({
    super.key,
    required this.isServerStarting,
    required this.serverStatus,
    required this.onShowConsole,
    required this.onConnectDatabase,
  });

  @override
  Widget build(BuildContext context) {
    final bool isBackendOnline =
        serverStatus.startsWith("Connected") || serverStatus == "Database Offline";

    Color bannerBgStart;
    Color bannerBgEnd;
    IconData bannerIcon;
    Color bannerIconColor;
    String bannerText;
    Widget bannerAction;

    if (isServerStarting) {
      bannerBgStart = const Color(0xFF1E3A8A); // Blue
      bannerBgEnd = const Color(0xFF0F172A);
      bannerIcon = Icons.info_outline_rounded;
      bannerIconColor = AppTheme.accentWarm;
      bannerText = 'Locating environment and launching FastAPI backend API server...';
      bannerAction = TextButton.icon(
        onPressed: onShowConsole,
        icon: const Icon(Icons.terminal_rounded, size: 14),
        label: const Text('Open Console', style: TextStyle(fontSize: 12)),
        style: TextButton.styleFrom(
          foregroundColor: AppTheme.accentWarm,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        ),
      );
    } else if (isBackendOnline) {
      bannerBgStart = const Color(0xFF78350F); // Amber / Brown-orange
      bannerBgEnd = const Color(0xFF0F172A);
      bannerIcon = Icons.cloud_off_rounded;
      bannerIconColor = AppTheme.accentWarm;
      bannerText = 'FastAPI server is running, but database is disconnected. Connect to initialize agent.';
      bannerAction = TextButton.icon(
        onPressed: onConnectDatabase,
        icon: const Icon(Icons.link_rounded, size: 14),
        label: const Text('Connect Database', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
        style: TextButton.styleFrom(
          foregroundColor: AppTheme.accentWarm,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        ),
      );
    } else {
      bannerBgStart = const Color(0xFF7F1D1D); // Red
      bannerBgEnd = const Color(0xFF0F172A);
      bannerIcon = Icons.warning_amber_rounded;
      bannerIconColor = AppTheme.accentCoral;
      bannerText = 'Backend offline or failed to start automatically. Please check logs for details.';
      bannerAction = TextButton.icon(
        onPressed: onShowConsole,
        icon: const Icon(Icons.terminal_rounded, size: 14),
        label: const Text('Open Console', style: TextStyle(fontSize: 12)),
        style: TextButton.styleFrom(
          foregroundColor: AppTheme.accentCoral,
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
          bannerAction,
        ],
      ),
    );
  }
}

class IndexingStatusBanner extends StatelessWidget {
  final String indexingMessage;

  const IndexingStatusBanner({
    super.key,
    required this.indexingMessage,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
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
              color: AppTheme.accentSecondary.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Center(
              child: SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation<Color>(AppTheme.accentSecondary),
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
                    color: AppTheme.accentSecondary,
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                    letterSpacing: 0.3,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  indexingMessage,
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
    );
  }
}
