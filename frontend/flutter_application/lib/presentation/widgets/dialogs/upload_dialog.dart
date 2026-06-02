import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../controllers/chat_controller.dart';

class UploadDialog extends StatefulWidget {
  final ChatController controller;

  const UploadDialog({
    super.key,
    required this.controller,
  });

  @override
  State<UploadDialog> createState() => _UploadDialogState();
}

class _UploadDialogState extends State<UploadDialog> {
  final TextEditingController _apiKeyController = TextEditingController();
  bool _profilesFetched = false;

  @override
  void initState() {
    super.initState();
    _fetchProfiles();
  }

  void _fetchProfiles() {
    if (!_profilesFetched && !widget.controller.isLoadingProfiles) {
      _profilesFetched = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        widget.controller.fetchChromeProfiles();
      });
    }
  }

  @override
  void dispose() {
    _apiKeyController.dispose();
    super.dispose();
  }

  Future<void> _handleManualUpload() async {
    try {
      FilePickerResult? result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['csv', 'html'],
      );

      if (result == null) return;

      final file = result.files.single;
      final apiKey = _apiKeyController.text.trim();

      if (kIsWeb) {
        if (file.bytes != null) {
          await widget.controller.uploadCSV(
            apiKey,
            file.bytes!,
            file.name,
            null,
          );
        }
      } else {
        if (file.path != null) {
          await widget.controller.uploadCSV(
            apiKey,
            [],
            file.name,
            file.path,
          );
        }
      }
    } catch (e) {
      debugPrint('Error picking file: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.controller,
      builder: (context, _) {
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
                child: const Icon(Icons.history_toggle_off_rounded,
                    color: AppTheme.accentPrimary, size: 24),
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
                      color: AppTheme.bgDeep,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: AppTheme.accentWarm.withValues(alpha: 0.2)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Row(
                          children: [
                            Icon(Icons.cloud_download_rounded, color: AppTheme.accentWarm, size: 20),
                            SizedBox(width: 8),
                            Text(
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
                          controller: _apiKeyController,
                          style: const TextStyle(color: Colors.white, fontSize: 12.5),
                          decoration: InputDecoration(
                            labelText: 'YouTube API Key (Optional)',
                            labelStyle: const TextStyle(color: Colors.white54, fontSize: 12),
                            hintText: 'AIza...',
                            hintStyle: const TextStyle(color: Colors.white24, fontSize: 12),
                            filled: true,
                            fillColor: AppTheme.bgCard,
                            isDense: true,
                            border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                            enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(10),
                              borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.08)),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(10),
                              borderSide: const BorderSide(color: AppTheme.accentWarm, width: 1.5),
                            ),
                          ),
                          obscureText: true,
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          width: double.infinity,
                          child: ElevatedButton.icon(
                            icon: const Icon(Icons.file_open_outlined, size: 16),
                            label: const Text('Pick Takeout & Upload',
                                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppTheme.accentWarm,
                              foregroundColor: Colors.black87,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                              padding: const EdgeInsets.symmetric(vertical: 12),
                              elevation: 2,
                            ),
                            onPressed: () {
                              Navigator.pop(context);
                              _handleManualUpload();
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
                      color: AppTheme.bgDeep,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: AppTheme.accentSecondary.withValues(alpha: 0.2)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Row(
                          children: [
                            Icon(Icons.chrome_reader_mode_rounded,
                                color: AppTheme.accentSecondary, size: 20),
                            SizedBox(width: 8),
                            Text(
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
                        if (widget.controller.isLoadingProfiles)
                          const Row(
                            children: [
                              SizedBox(
                                width: 14,
                                height: 14,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor:
                                      AlwaysStoppedAnimation<Color>(AppTheme.accentSecondary),
                                ),
                              ),
                              SizedBox(width: 8),
                              Text(
                                'Discovering local Chrome profiles...',
                                style: TextStyle(fontSize: 11.5, color: Colors.white54),
                              ),
                            ],
                          )
                        else if (widget.controller.chromeProfiles.isEmpty)
                          const Text(
                            '⚠️ No local Chrome profiles auto-discovered.',
                            style: TextStyle(fontSize: 11.5, color: AppTheme.accentCoral),
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
                              color: AppTheme.bgCard,
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
                            ),
                            child: DropdownButtonHideUnderline(
                              child: DropdownButton<String>(
                                value: widget.controller.selectedChromeProfile,
                                dropdownColor: AppTheme.bgCard,
                                isExpanded: true,
                                icon: const Icon(Icons.arrow_drop_down,
                                    color: AppTheme.accentSecondary),
                                style: const TextStyle(color: Colors.white, fontSize: 13),
                                items: widget.controller.chromeProfiles.map((String profile) {
                                  return DropdownMenuItem<String>(
                                    value: profile,
                                    child: Text(profile),
                                  );
                                }).toList(),
                                onChanged: (String? newValue) {
                                  widget.controller.selectChromeProfile(newValue);
                                },
                              ),
                            ),
                          ),
                          const SizedBox(height: 12),
                          SizedBox(
                            width: double.infinity,
                            child: ElevatedButton.icon(
                              icon: const Icon(Icons.bolt, size: 16),
                              label: const Text('⚡ 1-Click Auto Ingest',
                                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                              style: ElevatedButton.styleFrom(
                                backgroundColor: AppTheme.accentSecondary,
                                foregroundColor: Colors.black87,
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                                padding: const EdgeInsets.symmetric(vertical: 12),
                                elevation: 2,
                              ),
                              onPressed: widget.controller.selectedChromeProfile == null
                                  ? null
                                  : () {
                                      Navigator.pop(context);
                                      widget.controller.autoIngestChrome(
                                          widget.controller.selectedChromeProfile!);
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
                              _handleManualUpload();
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
  }
}
