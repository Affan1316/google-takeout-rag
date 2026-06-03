import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import '../models/chat_session_model.dart';
import '../models/db_credentials_model.dart';

class LocalHistoryDataSource {
  static const String _fileName = 'chat_sessions.json';
  static const String _credsFileName = 'db_credentials.json';

  Future<File> _getHistoryFile() async {
    final directory = await getApplicationDocumentsDirectory();
    return File('${directory.path}/$_fileName');
  }

  Future<File> _getCredsFile() async {
    final directory = await getApplicationDocumentsDirectory();
    return File('${directory.path}/$_credsFileName');
  }

  Future<DbCredentialsModel?> loadCredentials() async {
    try {
      final file = await _getCredsFile();
      if (!await file.exists()) {
        return null;
      }
      final contents = await file.readAsString();
      return DbCredentialsModel.fromJson(
          jsonDecode(contents) as Map<String, dynamic>);
    } catch (e) {
      debugPrint('Error loading db credentials: $e');
      return null;
    }
  }

  Future<void> saveCredentials(DbCredentialsModel creds) async {
    try {
      final file = await _getCredsFile();
      await file.writeAsString(jsonEncode(creds.toJson()));
    } catch (e) {
      debugPrint('Error saving db credentials: $e');
    }
  }

  Future<void> deleteCredentials() async {
    try {
      final file = await _getCredsFile();
      if (await file.exists()) {
        await file.delete();
      }
    } catch (e) {
      debugPrint('Error deleting db credentials: $e');
    }
  }

  Future<List<ChatSessionModel>> loadSessions() async {
    try {
      final file = await _getHistoryFile();
      if (!await file.exists()) {
        return [];
      }
      final contents = await file.readAsString();
      final List<dynamic> jsonList = jsonDecode(contents);
      final sessions = jsonList
          .map((json) => ChatSessionModel.fromJson(json as Map<String, dynamic>))
          .toList();

      // Sort sessions by lastActive (descending: newest first)
      sessions.sort((a, b) => b.lastActive.compareTo(a.lastActive));
      return sessions;
    } catch (e) {
      debugPrint('Error loading chat history: $e');
      return [];
    }
  }

  Future<void> saveSessions(List<ChatSessionModel> sessions) async {
    try {
      final file = await _getHistoryFile();
      final List<Map<String, dynamic>> jsonList =
          sessions.map((s) => s.toJson()).toList();
      await file.writeAsString(jsonEncode(jsonList));
    } catch (e) {
      debugPrint('Error saving chat history: $e');
    }
  }
}
