import 'dart:convert';
import 'package:http/http.dart' as http;
import '../../core/constants/endpoints.dart';
import '../models/chat_session_model.dart';

class BackendApiDataSource {
  Future<bool> checkBackendOnline() async {
    try {
      final response = await http
          .get(Uri.parse(Endpoints.status))
          .timeout(const Duration(seconds: 1));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>> fetchBackendStatus() async {
    final response = await http.get(Uri.parse(Endpoints.status));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception('Failed to fetch status: ${response.statusCode}');
    }
  }

  Future<bool> connectDatabase({
    required String projectRef,
    required String password,
    required String host,
    required String port,
    required String llmApiKey,
  }) async {
    final response = await http.post(
      Uri.parse(Endpoints.connectDb),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'db_project_ref': projectRef,
        'db_password': password,
        'db_host': host,
        'db_port': port,
        'llm_api_key': llmApiKey,
      }),
    );
    return response.statusCode == 200;
  }

  Future<bool> disconnectDatabase() async {
    try {
      final response = await http.post(
        Uri.parse(Endpoints.disconnectDb),
        headers: {'Content-Type': 'application/json'},
      );
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<List<String>> fetchChromeProfiles() async {
    final response = await http.get(Uri.parse(Endpoints.chromeProfiles));
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final List<dynamic> profilesList = data['profiles'] ?? [];
      return profilesList.map((e) => e.toString()).toList();
    } else {
      throw Exception('Failed to fetch profiles: ${response.statusCode}');
    }
  }

  Future<Map<String, dynamic>> autoIngestChrome(String profile) async {
    final response = await http.post(
      Uri.parse(Endpoints.ingestChromeLocal),
      body: {'profile': profile},
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      final data = jsonDecode(response.body);
      throw Exception(data['detail'] ?? 'Auto-Ingest failed with status ${response.statusCode}');
    }
  }

  Future<Map<String, dynamic>> uploadCSV({
    required String apiKey,
    required List<int> bytes,
    required String filename,
    required String? path,
  }) async {
    var request = http.MultipartRequest('POST', Uri.parse(Endpoints.uploadCsv));
    request.fields['api_key'] = apiKey;

    if (bytes.isNotEmpty) {
      request.files.add(
        http.MultipartFile.fromBytes(
          'file',
          bytes,
          filename: filename,
        ),
      );
    } else if (path != null && path.isNotEmpty) {
      request.files.add(
        await http.MultipartFile.fromPath(
          'file',
          path,
          filename: filename,
        ),
      );
    } else {
      throw Exception('No file payload was provided');
    }

    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      final data = jsonDecode(response.body);
      throw Exception(data['detail'] ?? 'Upload failed with status ${response.statusCode}');
    }
  }

  Future<Map<String, dynamic>> sendChatMessage(String text) async {
    final response = await http.post(
      Uri.parse(Endpoints.chat),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'query': text}),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception('Chat response failed with status ${response.statusCode}');
    }
  }

  Future<Map<String, dynamic>> analyzeTaxonomyDrift() async {
    final response = await http.get(Uri.parse(Endpoints.driftAnalysis));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception('Drift analysis failed with status ${response.statusCode}');
    }
  }

  Future<Map<String, dynamic>> applyTaxonomyDrift(List<String> categories) async {
    final response = await http.post(
      Uri.parse(Endpoints.applyDrift),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'categories': categories}),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      final data = jsonDecode(response.body);
      throw Exception(data['detail'] ?? 'Apply drift failed with status ${response.statusCode}');
    }
  }

  Future<List<ChatSessionModel>> fetchSessionsFromSupabase() async {
    final response = await http.get(Uri.parse(Endpoints.chatSessions));
    if (response.statusCode == 200) {
      final List<dynamic> jsonList = jsonDecode(response.body);
      return jsonList
          .map((json) => ChatSessionModel.fromJson(json as Map<String, dynamic>))
          .toList();
    } else {
      throw Exception('Fetch sessions from Supabase failed with status ${response.statusCode}');
    }
  }

  Future<bool> uploadSessionToSupabase(ChatSessionModel session) async {
    final response = await http.post(
      Uri.parse(Endpoints.chatSessions),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(session.toJson()),
    );
    return response.statusCode == 200;
  }

  Future<bool> deleteSessionFromSupabase(String id) async {
    final response = await http.delete(
      Uri.parse('${Endpoints.chatSessions}/$id'),
    );
    return response.statusCode == 200;
  }
}
