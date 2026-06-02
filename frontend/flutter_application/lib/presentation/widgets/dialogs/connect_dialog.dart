import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../controllers/chat_controller.dart';

class ConnectDialog extends StatefulWidget {
  final ChatController controller;

  const ConnectDialog({
    super.key,
    required this.controller,
  });

  @override
  State<ConnectDialog> createState() => _ConnectDialogState();
}

class _ConnectDialogState extends State<ConnectDialog> {
  late final TextEditingController _dbUrlController;
  late final TextEditingController _dbPasswordController;
  late final TextEditingController _llmApiKeyController;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _dbUrlController = TextEditingController();
    _dbPasswordController = TextEditingController();
    _llmApiKeyController = TextEditingController();
    _loadSavedCredentials();
  }

  Future<void> _loadSavedCredentials() async {
    final savedCreds = await widget.controller.getSavedCredentials();
    if (mounted) {
      setState(() {
        if (savedCreds != null) {
          _dbUrlController.text = savedCreds.url;
          _dbPasswordController.text = savedCreds.password;
          _llmApiKeyController.text = savedCreds.llmApiKey;
        }
        _isLoading = false;
      });
    }
  }

  @override
  void dispose() {
    _dbUrlController.dispose();
    _dbPasswordController.dispose();
    _llmApiKeyController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.controller.isConnectingDb) {
      return AlertDialog(
        backgroundColor: AppTheme.bgCard,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: AppTheme.accentPrimary.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(
                  strokeWidth: 2.5,
                  valueColor: AlwaysStoppedAnimation<Color>(AppTheme.accentPrimary),
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
              foregroundColor: AppTheme.accentPrimary,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
            ),
            onPressed: () => Navigator.pop(context),
            child: const Text('OK', style: TextStyle(fontWeight: FontWeight.bold)),
          ),
        ],
      );
    }

    if (_isLoading) {
      return const Center(
        child: CircularProgressIndicator(
          valueColor: AlwaysStoppedAnimation<Color>(AppTheme.accentPrimary),
        ),
      );
    }

    return AlertDialog(
      backgroundColor: AppTheme.bgCard,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      title: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: AppTheme.accentPrimary.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.security, color: AppTheme.accentPrimary, size: 24),
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
              controller: _dbUrlController,
              style: const TextStyle(color: Colors.white),
              decoration: InputDecoration(
                labelText: 'Connection URL',
                labelStyle: const TextStyle(color: Colors.white54),
                hintText: 'postgresql://postgres.[REF]:[PASS]@[HOST]:[PORT]/postgres',
                hintStyle: const TextStyle(color: Colors.white24),
                filled: true,
                fillColor: AppTheme.bgDeep,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.08))),
                focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: AppTheme.accentPrimary, width: 1.5)),
              ),
            ),
            const SizedBox(height: 14),
            TextField(
              controller: _dbPasswordController,
              style: const TextStyle(color: Colors.white),
              decoration: InputDecoration(
                labelText: 'Raw Database Password',
                labelStyle: const TextStyle(color: Colors.white54),
                hintText: 'e.g. Fz5f9\$E2-#xbq!U',
                hintStyle: const TextStyle(color: Colors.white24),
                filled: true,
                fillColor: AppTheme.bgDeep,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.08))),
                focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: AppTheme.accentPrimary, width: 1.5)),
              ),
              obscureText: true,
            ),
            const SizedBox(height: 22),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: AppTheme.accentSecondary.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Text(
                '🧠  Provide your DeepSeek LLM API Key for taxonomy drift analysis & RAG reasoning.',
                style: TextStyle(fontSize: 13, color: AppTheme.accentSecondary, height: 1.5),
              ),
            ),
            const SizedBox(height: 14),
            TextField(
              controller: _llmApiKeyController,
              style: const TextStyle(color: Colors.white),
              decoration: InputDecoration(
                labelText: 'DeepSeek API Key',
                labelStyle: const TextStyle(color: Colors.white54),
                hintText: 'sk-...',
                hintStyle: const TextStyle(color: Colors.white24),
                filled: true,
                fillColor: AppTheme.bgDeep,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.08))),
                focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: AppTheme.accentSecondary, width: 1.5)),
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
            backgroundColor: AppTheme.accentPrimary,
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
            elevation: 4,
          ),
          onPressed: () {
            Navigator.pop(context);
            widget.controller.connectToDatabase(
              _dbUrlController.text.trim(),
              _dbPasswordController.text.trim(),
              _llmApiKeyController.text.trim(),
            );
          },
          child: const Text(
            'Connect & Initialize',
            style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 0.3),
          ),
        ),
      ],
    );
  }
}
