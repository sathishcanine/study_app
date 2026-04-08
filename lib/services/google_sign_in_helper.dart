import 'package:google_sign_in/google_sign_in.dart';
import 'package:study_app/constants.dart';

/// Lazily configured [GoogleSignIn] using [googleWebClientId] as [serverClientId]
/// so the plugin returns an ID token for the Python backend.
GoogleSignIn createGoogleSignIn() {
  final webId = googleWebClientId();
  return GoogleSignIn(
    scopes: const ['email', 'profile'],
    serverClientId: webId.isEmpty ? null : webId,
  );
}
