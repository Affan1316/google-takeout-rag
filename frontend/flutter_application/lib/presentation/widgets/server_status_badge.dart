import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';

class ServerStatusBadge extends StatelessWidget {
  final bool isConnected;
  final bool isServerStarting;
  final String serverStatus;

  const ServerStatusBadge({
    super.key,
    required this.isConnected,
    required this.isServerStarting,
    required this.serverStatus,
  });

  @override
  Widget build(BuildContext context) {
    Color badgeColor;
    IconData badgeIcon;
    bool shouldGlow = false;

    if (isConnected) {
      badgeColor = AppTheme.accentTertiary; // Emerald success
      badgeIcon = Icons.check_circle_rounded;
    } else if (isServerStarting) {
      badgeColor = AppTheme.accentWarm; // Amber starting
      badgeIcon = Icons.sync_rounded;
      shouldGlow = true;
    } else {
      badgeColor = AppTheme.accentCoral; // Coral error
      badgeIcon = Icons.error_outline_rounded;
    }

    return Container(
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
          if (isServerStarting)
            const SizedBox(
              width: 12,
              height: 12,
              child: CircularProgressIndicator(
                strokeWidth: 2.0,
                valueColor: AlwaysStoppedAnimation<Color>(AppTheme.accentWarm),
              ),
            )
          else
            Icon(badgeIcon, color: badgeColor, size: 14),
          const SizedBox(width: 6),
          Text(
            serverStatus,
            style: TextStyle(
              color: badgeColor,
              fontSize: 12,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }
}
