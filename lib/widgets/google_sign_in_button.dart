import 'package:flutter/material.dart';
import 'package:study_app/constants.dart';

class GoogleSignInButton extends StatelessWidget {
  const GoogleSignInButton({
    super.key,
    required this.onPressed,
    this.label = 'Continue with Google',
    this.enabled = true,
  });

  final VoidCallback onPressed;
  final String label;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 30),
      child: OutlinedButton(
        style: OutlinedButton.styleFrom(
          backgroundColor: Colors.white,
          foregroundColor: const Color(0xff2B262D),
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
          side: BorderSide(color: Colors.grey.shade400),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
        onPressed: enabled ? onPressed : null,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: const Color(0xFF4285F4)),
              ),
              child: const Center(
                child: Text(
                  'G',
                  style: TextStyle(
                    color: Color(0xFF4285F4),
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Text(
              label,
              style: TextStyle(
                fontFamily: kFontText,
                fontWeight: FontWeight.w600,
                fontSize: 16,
                color: enabled ? const Color(0xff2B262D) : Colors.grey,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
