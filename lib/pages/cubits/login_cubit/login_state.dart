part of 'login_cubit.dart';

sealed class LoginState {}

final class LoginInitial extends LoginState {}

final class LoginSuccess extends LoginState {
  LoginSuccess({this.email});
  final String? email;
}

final class LoginFailure extends LoginState {
  final String errMessage;
  LoginFailure({required this.errMessage});
}

final class LoginLoading extends LoginState {}
