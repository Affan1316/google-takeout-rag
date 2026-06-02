import '../../domain/entities/chat_session.dart';
import 'chat_message_model.dart';

class ChatSessionModel extends ChatSession {
  ChatSessionModel({
    required super.id,
    required super.title,
    required super.lastActive,
    required super.messages,
  });

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'lastActive': lastActive.toIso8601String(),
        'messages': messages
            .map((m) => ChatMessageModel.fromEntity(m).toJson())
            .toList(),
      };

  factory ChatSessionModel.fromJson(Map<String, dynamic> json) {
    return ChatSessionModel(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      lastActive: json['lastActive'] != null
          ? DateTime.parse(json['lastActive'] as String)
          : DateTime.now(),
      messages: (json['messages'] as List<dynamic>?)
              ?.map((m) => ChatMessageModel.fromJson(m as Map<String, dynamic>))
              .toList() ??
          [],
    );
  }

  factory ChatSessionModel.fromEntity(ChatSession entity) {
    return ChatSessionModel(
      id: entity.id,
      title: entity.title,
      lastActive: entity.lastActive,
      messages: entity.messages,
    );
  }
}
