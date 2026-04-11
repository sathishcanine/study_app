import 'dart:io';

import 'package:flutter/material.dart';

/// Override with `--dart-define=API_BASE_URL=https://api.example.com`
String apiBaseUrl() {
  const fromEnv = String.fromEnvironment('API_BASE_URL');
  if (fromEnv.isNotEmpty) return fromEnv;
  if (Platform.isAndroid) return 'http://192.168.1.7:8000';
  // if (Platform.isAndroid) return 'http://10.60.121.204:8000';
  return 'http://192.168.1.7:8000';
}

/// Web OAuth client ID from Google Cloud Console (OAuth 2.0 Web application).
/// Override with `--dart-define=GOOGLE_WEB_CLIENT_ID=...` if you use a different client.
const String kDefaultGoogleWebClientId =
    '644097932381-jmd5k911215rn19237e5kbapge7qokog.apps.googleusercontent.com';

String googleWebClientId() {
  const fromEnv = String.fromEnvironment('GOOGLE_WEB_CLIENT_ID');
  if (fromEnv.isNotEmpty) return fromEnv;
  return kDefaultGoogleWebClientId;
}

Color kPrimaryColor = const Color(0xFFA76AE4);
Color kSecondaryColor = const Color(0xFFC7A8FC);
Color kTextAccent = const Color(0xFF8251DE);
String kFontText = 'Poppins';
String kLogo = "assets/images/logo.png";
