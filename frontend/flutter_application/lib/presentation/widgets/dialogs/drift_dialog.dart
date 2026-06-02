import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../controllers/chat_controller.dart';

class DriftDialog extends StatefulWidget {
  final ChatController controller;

  const DriftDialog({
    super.key,
    required this.controller,
  });

  @override
  State<DriftDialog> createState() => _DriftDialogState();
}

enum DriftDialogState { loading, intact, checklist, error }

class _DriftDialogState extends State<DriftDialog> {
  DriftDialogState _dialogState = DriftDialogState.loading;
  String _message = "";
  List<String> _suggestedCats = [];
  List<String> _selectedCategories = [];
  List<dynamic> _sampleLogs = [];
  String _errorMsg = "";

  @override
  void initState() {
    super.initState();
    _runAnalysis();
  }

  Future<void> _runAnalysis() async {
    try {
      final data = await widget.controller.runDriftAnalysis();
      final bool driftFound = data['drift_found'] ?? false;
      final List<dynamic> suggested = data['suggested_categories'] ?? [];
      final List<dynamic> samples = data['drifted_logs_sample'] ?? [];
      final String msg = data['message'] ?? "";

      if (mounted) {
        setState(() {
          _message = msg;
          _sampleLogs = samples;
          _suggestedCats = suggested.map((e) => e.toString()).toList();
          _selectedCategories = List.from(_suggestedCats);

          if (!driftFound || _suggestedCats.isEmpty) {
            _dialogState = DriftDialogState.intact;
            _message = msg.isNotEmpty
                ? msg
                : "No taxonomy drift found! Your current interests cover your activity well.";
          } else {
            _dialogState = DriftDialogState.checklist;
          }
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMsg = e.toString();
          _dialogState = DriftDialogState.error;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    switch (_dialogState) {
      case DriftDialogState.loading:
        return AlertDialog(
          backgroundColor: AppTheme.bgCard,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          content: const Row(
            children: [
              CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(AppTheme.accentSecondary)),
              SizedBox(width: 20),
              Text("Analyzing taxonomy drift & anomalies...", style: TextStyle(color: Colors.white70)),
            ],
          ),
        );

      case DriftDialogState.intact:
        return AlertDialog(
          backgroundColor: AppTheme.bgCard,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
          title: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.accentTertiary.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.check_circle_rounded, color: AppTheme.accentTertiary, size: 22),
              ),
              const SizedBox(width: 12),
              const Text("Taxonomy Intact", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ],
          ),
          content: Text(
            _message,
            style: const TextStyle(color: Colors.white60, height: 1.5),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text("Awesome",
                  style: TextStyle(color: AppTheme.accentTertiary, fontWeight: FontWeight.w600)),
            ),
          ],
        );

      case DriftDialogState.error:
        return AlertDialog(
          backgroundColor: AppTheme.bgCard,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
          title: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.accentCoral.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.error_rounded, color: AppTheme.accentCoral, size: 22),
              ),
              const SizedBox(width: 12),
              const Text("Drift Analysis Failed", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ],
          ),
          content: Text("Error: $_errorMsg", style: const TextStyle(color: Colors.white60, height: 1.4)),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text("Close",
                  style: TextStyle(color: AppTheme.accentCoral, fontWeight: FontWeight.w600)),
            ),
          ],
        );

      case DriftDialogState.checklist:
        return AlertDialog(
          backgroundColor: AppTheme.bgCard,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
          title: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.accentSecondary.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.psychology, color: AppTheme.accentSecondary, size: 24),
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
                      color: AppTheme.bgDeep,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: AppTheme.accentSecondary.withValues(alpha: 0.12)),
                    ),
                    child: Column(
                      children: _suggestedCats.map((cat) {
                        final String category = cat;
                        final bool isSelected = _selectedCategories.contains(category);
                        return CheckboxListTile(
                          activeColor: AppTheme.accentSecondary,
                          checkColor: AppTheme.bgDeep,
                          title: Text(category,
                              style: const TextStyle(
                                  color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500)),
                          value: isSelected,
                          onChanged: (bool? checked) {
                            setState(() {
                              if (checked == true) {
                                _selectedCategories.add(category);
                              } else {
                                _selectedCategories.remove(category);
                              }
                            });
                          },
                        );
                      }).toList(),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // Sample Drifted Logs
                  if (_sampleLogs.isNotEmpty) ...[
                    const Text(
                      "SAMPLE OF UNMATCHED LOGS",
                      style: TextStyle(
                          color: AppTheme.accentSecondary,
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 1.2),
                    ),
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppTheme.bgDeep,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: Colors.white.withValues(alpha: 0.05)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: _sampleLogs.map((log) {
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
                                      color: source == 'youtube' ? AppTheme.accentCoral : AppTheme.accentWarm,
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
                                  style: TextStyle(
                                      color: Colors.white.withValues(alpha: 0.3), fontSize: 10),
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
                backgroundColor: AppTheme.accentSecondary,
                foregroundColor: AppTheme.bgDeep,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
                elevation: 4,
              ),
              onPressed: _selectedCategories.isEmpty
                  ? null
                  : () {
                      Navigator.pop(context);
                      widget.controller.applyDrift(_selectedCategories);
                    },
              child: const Text("Apply New Interests", style: TextStyle(fontWeight: FontWeight.bold)),
            ),
          ],
        );
    }
  }
}
