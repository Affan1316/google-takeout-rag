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
}
