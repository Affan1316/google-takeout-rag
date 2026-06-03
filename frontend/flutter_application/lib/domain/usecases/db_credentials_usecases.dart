import '../entities/db_credentials.dart';
import '../repositories/chat_history_repository.dart';
import '../repositories/backend_repository.dart';

class DbCredentialsUsecases {
  final ChatHistoryRepository historyRepository;
  final BackendRepository backendRepository;

  DbCredentialsUsecases({
    required this.historyRepository,
    required this.backendRepository,
  });

  Future<DbCredentials?> loadCredentials() async {
    return historyRepository.loadCredentials();
  }

  Future<void> saveCredentials(DbCredentials creds) async {
    await historyRepository.saveCredentials(creds);
  }

  Future<void> deleteCredentials() async {
    await historyRepository.deleteCredentials();
  }

  Future<bool> connectDatabase({
    required String projectRef,
    required String password,
    required String host,
    required String port,
    required String llmApiKey,
  }) async {
    return backendRepository.connectDatabase(
      projectRef: projectRef,
      password: password,
      host: host,
      port: port,
      llmApiKey: llmApiKey,
    );
  }
}
