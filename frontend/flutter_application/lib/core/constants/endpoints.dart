import 'dart:io' show Platform;
import 'package:flutter/foundation.dart' show kIsWeb;

class Endpoints {
  static String get baseUrl {
    if (kIsWeb) return 'http://127.0.0.1:8000';
    if (Platform.isAndroid) return 'http://10.0.2.2:8000';
    return 'http://127.0.0.1:8000';
  }

  static String get chat => '$baseUrl/chat';
  static String get uploadCsv => '$baseUrl/upload-and-process-csv';
  static String get connectDb => '$baseUrl/connect-db';
  static String get disconnectDb => '$baseUrl/disconnect-db';
  static String get status => '$baseUrl/status';
  static String get driftAnalysis => '$baseUrl/drift-analysis';
  static String get applyDrift => '$baseUrl/apply-drift';
  static String get chromeProfiles => '$baseUrl/chrome-profiles';
  static String get ingestChromeLocal => '$baseUrl/ingest-chrome-local';
  static String get chatSessions => '$baseUrl/chat-sessions';
}
