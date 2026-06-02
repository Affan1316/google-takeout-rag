import '../entities/chat_session.dart';
import '../repositories/chat_history_repository.dart';
import '../repositories/backend_repository.dart';

class ChatSessionsUsecases {
  final ChatHistoryRepository historyRepository;
  final BackendRepository backendRepository;

  ChatSessionsUsecases({
    required this.historyRepository,
    required this.backendRepository,
  });

  Future<List<ChatSession>> loadSessions() async {
    return historyRepository.loadSessions();
  }

  Future<void> saveSessions(List<ChatSession> sessions) async {
    await historyRepository.saveSessions(sessions);
  }

  Future<List<ChatSession>> fetchSessionsFromSupabase() async {
    return backendRepository.fetchSessionsFromSupabase();
  }

  Future<bool> uploadSessionToSupabase(ChatSession session) async {
    return backendRepository.uploadSessionToSupabase(session);
  }

  Future<bool> deleteSessionFromSupabase(String id) async {
    return backendRepository.deleteSessionFromSupabase(id);
  }
}
