import '../entities/chat_session.dart';

abstract class BackendRepository {
  Future<bool> checkBackendOnline();
  Future<Map<String, dynamic>> fetchBackendStatus();
  Future<void> startBackendProcess({
    required void Function(String) onLog,
    required void Function(int) onExit,
  });
  void shutdownBackendProcess();
  Future<void> cleanPortConflict();
  
  Future<bool> connectDatabase({
    required String projectRef,
    required String password,
    required String host,
    required String port,
    required String llmApiKey,
  });

  Future<List<String>> fetchChromeProfiles();
  Future<Map<String, dynamic>> autoIngestChrome(String profile);
  
  Future<Map<String, dynamic>> uploadCSV({
    required String apiKey,
    required List<int> bytes,
    required String filename,
    required String? path,
  });

  Future<Map<String, dynamic>> sendChatMessage(String text);
  Future<Map<String, dynamic>> analyzeTaxonomyDrift();
  Future<Map<String, dynamic>> applyTaxonomyDrift(List<String> categories);

  Future<List<ChatSession>> fetchSessionsFromSupabase();
  Future<bool> uploadSessionToSupabase(ChatSession session);
  Future<bool> deleteSessionFromSupabase(String id);
}
