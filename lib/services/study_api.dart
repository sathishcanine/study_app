import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:study_app/constants.dart';

class StudyApiException implements Exception {
  StudyApiException(this.message);
  final String message;
  @override
  String toString() => message;
}

class StudyApi {
  StudyApi({String? baseUrl})
      : _base = _normalizeBaseUrl(baseUrl ?? apiBaseUrl());

  final String _base;

  /// Avoids `//auth/...` when the base URL ends with `/` (which would 404 on the server).
  static String _normalizeBaseUrl(String raw) {
    return raw.trim().replaceAll(RegExp(r'/+$'), '');
  }

  Uri _u(String path) {
    final p = path.startsWith('/') ? path : '/$path';
    return Uri.parse('$_base$p');
  }

  static String _messageFromResponse(http.Response r) {
    try {
      final dynamic j = jsonDecode(r.body);
      if (j is Map && j['detail'] != null) {
        final d = j['detail'];
        if (d is String) return d;
        if (d is List && d.isNotEmpty) {
          final first = d.first;
          if (first is Map && first['msg'] != null) {
            return first['msg'].toString();
          }
        }
        return d.toString();
      }
    } catch (_) {}
    return 'Request failed (${r.statusCode})';
  }

  Future<Map<String, dynamic>> register({
    required String email,
    required String password,
    required String username,
    int score = 0,
  }) async {
    final response = await http.post(
      _u('/auth/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'email': email,
        'password': password,
        'username': username,
        'score': score,
      }),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw StudyApiException(_messageFromResponse(response));
  }

  Future<Map<String, dynamic>> login({
    required String email,
    required String password,
  }) async {
    final response = await http.post(
      _u('/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw StudyApiException(_messageFromResponse(response));
  }

  Future<Map<String, dynamic>> loginWithGoogle({required String idToken}) async {
    final response = await http.post(
      _u('/auth/google'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'id_token': idToken}),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw StudyApiException(_messageFromResponse(response));
  }

  Future<Map<String, dynamic>> getProfile(String token) async {
    final response = await http.get(
      _u('/users/me'),
      headers: {'Authorization': 'Bearer $token'},
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw StudyApiException(_messageFromResponse(response));
  }

  Future<void> recordQuizResult({
    required String token,
    required int earnedScore,
    required int questionNumbers,
    required int correctAnswers,
    required String catName,
    required int questionLength,
    required String difficulty,
    required DateTime date,
  }) async {
    final response = await http.post(
      _u('/users/me/quiz-result'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      },
      body: jsonEncode({
        'score': earnedScore,
        'question_numbers': questionNumbers,
        'correct_answers': correctAnswers,
        'cat_name': catName,
        'question_length': questionLength,
        'difficulty': difficulty,
        'date': date.toUtc().toIso8601String(),
      }),
    );
    if (response.statusCode != 200) {
      throw StudyApiException(_messageFromResponse(response));
    }
  }

  Future<List<Map<String, dynamic>>> getLeaderboard() async {
    final response = await http.get(_u('/leaderboard'));
    if (response.statusCode == 200) {
      final list = jsonDecode(response.body) as List<dynamic>;
      return list.map((e) => e as Map<String, dynamic>).toList();
    }
    throw StudyApiException(_messageFromResponse(response));
  }

  Future<Map<String, dynamic>> getSubjectSets({
    required String token,
    required String examType,
    required String subject,
  }) async {
    final response = await http.get(
      _u('/subjects/$subject/sets').replace(
        queryParameters: {
          'exam_type': examType,
        },
      ),
      headers: {'Authorization': 'Bearer $token'},
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw StudyApiException(_messageFromResponse(response));
  }

  Future<Map<String, dynamic>> getTopicQuestions({
    required String token,
    required String topicSlug,
    required String examType,
    required String subject,
    required int setNo,
    String lang = 'en',
  }) async {
    final response = await http.get(
      _u('/topics/$topicSlug/questions').replace(
        queryParameters: {
          'exam_type': examType,
          'subject': subject,
          'set_no': setNo.toString(),
          'lang': lang,
        },
      ),
      headers: {'Authorization': 'Bearer $token'},
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw StudyApiException(_messageFromResponse(response));
  }

  Future<Map<String, dynamic>> getCompletedTopicSets({
    required String token,
    required String examType,
    String? subject,
  }) async {
    final query = <String, String>{'exam_type': examType};
    if (subject != null && subject.isNotEmpty) {
      query['subject'] = subject;
    }
    final response = await http.get(
      _u('/users/me/completed-topic-sets').replace(queryParameters: query),
      headers: {'Authorization': 'Bearer $token'},
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw StudyApiException(_messageFromResponse(response));
  }

  Future<Map<String, dynamic>> submitTopicSetAttempt({
    required String token,
    required String setId,
    required int score,
    required int correctAnswers,
    required int totalQuestions,
  }) async {
    final response = await http.post(
      _u('/topic-sets/$setId/attempts'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      },
      body: jsonEncode({
        'score': score,
        'correct_answers': correctAnswers,
        'total_questions': totalQuestions,
      }),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw StudyApiException(_messageFromResponse(response));
  }

  Future<Map<String, dynamic>> getTopicSetLeaderboard({
    required String token,
    required String setId,
  }) async {
    final response = await http.get(
      _u('/topic-sets/$setId/leaderboard'),
      headers: {'Authorization': 'Bearer $token'},
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw StudyApiException(_messageFromResponse(response));
  }
}
