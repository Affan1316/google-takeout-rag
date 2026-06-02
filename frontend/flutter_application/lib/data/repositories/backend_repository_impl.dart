import '../../domain/entities/chat_session.dart';
import '../../domain/repositories/backend_repository.dart';
import '../datasources/backend_api_datasource.dart';
import '../datasources/backend_process_datasource.dart';
import '../models/chat_session_model.dart';

class BackendRepositoryImpl implements BackendRepository {
  final BackendApiDataSource apiDataSource;
  final BackendProcessDataSource processDataSource;

  BackendRepositoryImpl({
    required this.apiDataSource,
    required this.processDataSource,
  });

  @override
  Future<bool> checkBackendOnline() {
    return apiDataSource.checkBackendOnline();
  }

  @override
  Future<Map<String, dynamic>> fetchBackendStatus() {
    return apiDataSource.fetchBackendStatus();
  }

  @override
  Future<void> startBackendProcess({
    required void Function(String) onLog,
    required void Function(int) onExit,
  }) {
    return processDataSource.startProcess(onLog: onLog, onExit: onExit);
  }

  @override
  void shutdownBackendProcess() {
    processDataSource.shutdownProcess();
  }

  @override
  Future<void> cleanPortConflict() {
    return processDataSource.cleanPortConflict();
  }

  @override
  Future<bool> connectDatabase({
    required String projectRef,
    required String password,
    required String host,
    required String port,
    required String llmApiKey,
  }) {
    return apiDataSource.connectDatabase(
      projectRef: projectRef,
      password: password,
      host: host,
      port: port,
      llmApiKey: llmApiKey,
    );
  }

  @override
  Future<List<String>> fetchChromeProfiles() {
    return apiDataSource.fetchChromeProfiles();
  }

  @override
  Future<Map<String, dynamic>> autoIngestChrome(String profile) {
    return apiDataSource.autoIngestChrome(profile);
  }

  @override
  Future<Map<String, dynamic>> uploadCSV({
    required String apiKey,
    required List<int> bytes,
    required String filename,
    required String? path,
  }) {
    return apiDataSource.uploadCSV(
      apiKey: apiKey,
      bytes: bytes,
      filename: filename,
      path: path,
    );
  }

  @override
  Future<Map<String, dynamic>> sendChatMessage(String text) {
    return apiDataSource.sendChatMessage(text);
  }

  @override
  Future<Map<String, dynamic>> analyzeTaxonomyDrift() {
    return apiDataSource.analyzeTaxonomyDrift();
  }

  @override
  Future<Map<String, dynamic>> applyTaxonomyDrift(List<String> categories) {
    return apiDataSource.applyTaxonomyDrift(categories);
  }

  @override
  Future<List<ChatSession>> fetchSessionsFromSupabase() async {
    final models = await apiDataSource.fetchSessionsFromSupabase();
    return List<ChatSession>.from(models);
  }

  @override
  Future<bool> uploadSessionToSupabase(ChatSession session) {
    return apiDataSource.uploadSessionToSupabase(
      ChatSessionModel.fromEntity(session),
    );
  }

  @override
  Future<bool> deleteSessionFromSupabase(String id) {
    return apiDataSource.deleteSessionFromSupabase(id);
  }
}
