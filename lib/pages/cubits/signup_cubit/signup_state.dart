part of 'signup_cubit.dart';

sealed class SignupState {}

final class SignupInitial extends SignupState {}

final class SignupLoading extends SignupState {}

final class SignupSuccess extends SignupState {
  SignupSuccess({this.email});
  final String? email;
}

final class SignupFailure extends SignupState {
  final String errMessage;
  SignupFailure({required this.errMessage});
}
