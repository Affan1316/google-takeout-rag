import '../entities/chat_session.dart';
import '../entities/db_credentials.dart';

abstract class ChatHistoryRepository {
  Future<DbCredentials?> loadCredentials();
  Future<void> saveCredentials(DbCredentials creds);
  Future<List<ChatSession>> loadSessions();
  Future<void> saveSessions(List<ChatSession> sessions);
  Future<void> deleteCredentials();
}
