import '../../domain/entities/db_credentials.dart';

class DbCredentialsModel extends DbCredentials {
  DbCredentialsModel({
    required super.url,
    required super.password,
    required super.llmApiKey,
  });

  Map<String, dynamic> toJson() => {
        'url': url,
        'password': password,
        'llmApiKey': llmApiKey,
      };

  factory DbCredentialsModel.fromJson(Map<String, dynamic> json) {
    return DbCredentialsModel(
      url: json['url'] as String? ?? '',
      password: json['password'] as String? ?? '',
      llmApiKey: json['llmApiKey'] as String? ?? '',
    );
  }

  factory DbCredentialsModel.fromEntity(DbCredentials entity) {
    return DbCredentialsModel(
      url: entity.url,
      password: entity.password,
      llmApiKey: entity.llmApiKey,
    );
  }
}
