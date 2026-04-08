import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:study_app/constants.dart';
import 'package:study_app/services/auth_storage.dart';
import 'package:study_app/services/google_sign_in_helper.dart';
import 'package:study_app/services/study_api.dart';

part 'login_state.dart';

class LoginCubit extends Cubit<LoginState> {
  LoginCubit() : super(LoginInitial());

  Future<void> LoginUser({required email, required password}) async {
    emit(LoginLoading());
    try {
      final body = await StudyApi().login(email: email as String, password: password as String);
      final token = body['access_token'] as String;
      await AuthStorage.saveSession(token: token, email: email as String);
      emit(LoginSuccess());
    } on StudyApiException catch (e) {
      emit(LoginFailure(errMessage: e.message));
    } catch (e) {
      emit(LoginFailure(errMessage: e.toString()));
    }
  }

  Future<void> signInWithGoogle() async {
    emit(LoginLoading());
    try {
      if (googleWebClientId().isEmpty) {
        emit(LoginFailure(
            errMessage:
                'Set GOOGLE_WEB_CLIENT_ID when running the app (Web OAuth client ID from Google Cloud).'));
        return;
      }
      final google = createGoogleSignIn();
      final account = await google.signIn();
      if (account == null) {
        emit(LoginInitial());
        return;
      }
      final auth = await account.authentication;
      final idToken = auth.idToken;
      if (idToken == null || idToken.isEmpty) {
        emit(LoginFailure(
            errMessage:
                'No Google ID token. On iOS, set GIDClientID and URL scheme in Info.plist; use the same Web client ID here.'));
        return;
      }
      final body = await StudyApi().loginWithGoogle(idToken: idToken);
      final token = body['access_token'] as String;
      final email = body['email'] as String? ?? account.email;
      await AuthStorage.saveSession(token: token, email: email);
      emit(LoginSuccess(email: email));
    } on StudyApiException catch (e) {
      emit(LoginFailure(errMessage: e.message));
    } catch (e) {
      emit(LoginFailure(errMessage: e.toString()));
    }
  }

  @override
  void onChange(Change<LoginState> change) {
    super.onChange(change);
    print(change);
  }
}
