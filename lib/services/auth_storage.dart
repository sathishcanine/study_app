import 'package:shared_preferences/shared_preferences.dart';

class AuthStorage {
  static const _tokenKey = 'auth_token';
  static const _emailKey = 'auth_email';

  static Future<void> saveSession({required String token, required String email}) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_tokenKey, token);
    await p.setString(_emailKey, email);
  }

  static Future<String?> getToken() async {
    final p = await SharedPreferences.getInstance();
    return p.getString(_tokenKey);
  }

  static Future<String?> getEmail() async {
    final p = await SharedPreferences.getInstance();
    return p.getString(_emailKey);
  }

  static Future<void> clear() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_tokenKey);
    await p.remove(_emailKey);
  }
}
