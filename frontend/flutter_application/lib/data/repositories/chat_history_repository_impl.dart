import '../../domain/entities/chat_session.dart';
import '../../domain/entities/db_credentials.dart';
import '../../domain/repositories/chat_history_repository.dart';
import '../datasources/local_history_datasource.dart';
import '../models/chat_session_model.dart';
import '../models/db_credentials_model.dart';

class ChatHistoryRepositoryImpl implements ChatHistoryRepository {
  final LocalHistoryDataSource localDataSource;

  ChatHistoryRepositoryImpl({required this.localDataSource});

  @override
  Future<DbCredentials?> loadCredentials() async {
    return localDataSource.loadCredentials();
  }

  @override
  Future<void> saveCredentials(DbCredentials creds) async {
    await localDataSource.saveCredentials(DbCredentialsModel.fromEntity(creds));
  }

  @override
  Future<List<ChatSession>> loadSessions() async {
    final models = await localDataSource.loadSessions();
    return List<ChatSession>.from(models);
  }

  @override
  Future<void> saveSessions(List<ChatSession> sessions) async {
    final models = sessions.map((s) => ChatSessionModel.fromEntity(s)).toList();
    await localDataSource.saveSessions(models);
  }

  @override
  Future<void> deleteCredentials() async {
    await localDataSource.deleteCredentials();
  }
}
