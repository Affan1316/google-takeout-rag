import '../repositories/backend_repository.dart';

class BackendApiUsecases {
  final BackendRepository repository;

  BackendApiUsecases({required this.repository});

  Future<List<String>> fetchChromeProfiles() async {
    return repository.fetchChromeProfiles();
  }

  Future<Map<String, dynamic>> autoIngestChrome(String profile) async {
    return repository.autoIngestChrome(profile);
  }

  Future<Map<String, dynamic>> uploadCSV({
    required String apiKey,
    required List<int> bytes,
    required String filename,
    required String? path,
  }) async {
    return repository.uploadCSV(
      apiKey: apiKey,
      bytes: bytes,
      filename: filename,
      path: path,
    );
  }

  Future<Map<String, dynamic>> sendChatMessage(String text) async {
    return repository.sendChatMessage(text);
  }

  Future<Map<String, dynamic>> analyzeTaxonomyDrift() async {
    return repository.analyzeTaxonomyDrift();
  }

  Future<Map<String, dynamic>> applyTaxonomyDrift(List<String> categories) async {
    return repository.applyTaxonomyDrift(categories);
  }
}
