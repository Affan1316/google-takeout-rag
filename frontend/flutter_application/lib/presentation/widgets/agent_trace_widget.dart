import 'dart:convert';
import 'package:flutter/material.dart';

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
