import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:study_app/constants.dart';
import 'package:study_app/services/auth_storage.dart';
import 'package:study_app/services/google_sign_in_helper.dart';
import 'package:study_app/services/study_api.dart';

part 'signup_state.dart';

class SignupCubit extends Cubit<SignupState> {
  SignupCubit() : super(SignupInitial());

  Future<void> signUpUser(
      {required String userName,
      required String email,
      required password,
      required int score}) async {
    emit(SignupLoading());
    try {
      final body = await StudyApi().register(
        email: email,
        password: password as String,
        username: userName,
        score: score,
      );
      final token = body['access_token'] as String;
      await AuthStorage.saveSession(token: token, email: email);
      emit(SignupSuccess());
    } on StudyApiException catch (e) {
      final msg = e.message.toLowerCase();
      if (msg.contains('email') && msg.contains('format')) {
        emit(SignupFailure(errMessage: 'The email address is badly formatted.'));
      } else if (msg.contains('password') && msg.contains('short')) {
        emit(SignupFailure(errMessage: 'The password provided is too weak.'));
      } else if (msg.contains('already exists')) {
        emit(SignupFailure(
            errMessage: 'The account already exists for that email.'));
      } else {
        emit(SignupFailure(errMessage: e.message));
      }
    } catch (e) {
      print(e);
      emit(SignupFailure(errMessage: e.toString()));
    }
  }

  Future<void> signUpWithGoogle() async {
    emit(SignupLoading());
    try {
      if (googleWebClientId().isEmpty) {
        emit(SignupFailure(
            errMessage:
                'Set GOOGLE_WEB_CLIENT_ID when running the app (Web OAuth client ID from Google Cloud).'));
        return;
      }
      final google = createGoogleSignIn();
      final account = await google.signIn();
      if (account == null) {
        emit(SignupInitial());
        return;
      }
      final auth = await account.authentication;
      final idToken = auth.idToken;
      if (idToken == null || idToken.isEmpty) {
        emit(SignupFailure(
            errMessage:
                'No Google ID token. On iOS, set GIDClientID and URL scheme in Info.plist.'));
        return;
      }
      final body = await StudyApi().loginWithGoogle(idToken: idToken);
      final token = body['access_token'] as String;
      final email = body['email'] as String? ?? account.email;
      await AuthStorage.saveSession(token: token, email: email);
      emit(SignupSuccess(email: email));
    } on StudyApiException catch (e) {
      emit(SignupFailure(errMessage: e.message));
    } catch (e) {
      emit(SignupFailure(errMessage: e.toString()));
    }
  }
}
