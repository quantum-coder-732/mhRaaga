import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// The live mhRaaga cloud: CloudFront → API Gateway → Lambda → DynamoDB.
const kBase = 'https://d1bka1wc4jd8uy.cloudfront.net';

class ApiError implements Exception {
  ApiError(this.message, [this.status = 0]);
  final String message;
  final int status;
  @override
  String toString() => message;
}

class Api {
  static String? token;
  static Map<String, dynamic>? user;

  static Future<void> restore() async {
    final p = await SharedPreferences.getInstance();
    token = p.getString('token');
    final u = p.getString('user');
    if (u != null) user = jsonDecode(u) as Map<String, dynamic>;
  }

  static Future<void> _save() async {
    final p = await SharedPreferences.getInstance();
    if (token == null) {
      await p.remove('token');
      await p.remove('user');
    } else {
      await p.setString('token', token!);
      await p.setString('user', jsonEncode(user));
    }
  }

  static Future<dynamic> call(String method, String path, {Object? body, bool auth = true}) async {
    final uri = Uri.parse('$kBase/api$path');
    final headers = {'Content-Type': 'application/json', if (auth && token != null) 'Authorization': 'Bearer $token'};
    try {
      final r = await (method == 'POST'
              ? http.post(uri, headers: headers, body: jsonEncode(body))
              : method == 'DELETE'
                  ? http.delete(uri, headers: headers)
                  : http.get(uri, headers: headers))
          .timeout(const Duration(seconds: 60));
      dynamic data = {};
      try {
        data = jsonDecode(utf8.decode(r.bodyBytes));
      } catch (_) {}
      if (r.statusCode == 401 && token != null && auth) {
        await signOut();
        throw ApiError((data is Map ? data['error'] : null) ?? 'Please sign in again.', 401);
      }
      if (r.statusCode >= 400) throw ApiError((data is Map ? data['error'] : null) ?? 'Error ${r.statusCode}', r.statusCode);
      return data;
    } on ApiError {
      rethrow;
    } catch (e) {
      throw ApiError('Could not reach mhRaaga. Check your connection.');
    }
  }

  static Future<void> login(String email, String pw) async {
    final d = await call('POST', '/auth/login', body: {'email': email, 'password': pw}, auth: false);
    token = d['token'];
    user = Map<String, dynamic>.from(d['user']);
    await _save();
  }

  static Future<void> signup(String name, String email, String pw) async {
    final d = await call('POST', '/auth/signup', body: {'name': name, 'email': email, 'password': pw}, auth: false);
    token = d['token'];
    user = Map<String, dynamic>.from(d['user']);
    await _save();
  }

  static Future<void> signOut() async {
    token = null;
    user = null;
    await _save();
  }
}
