// Sample obfuscated Java file (Phase 8)
// Combines multiple obfuscation layers:
// 1. Base64 decoder: Base64.getDecoder().decode(...)
// 2. Integer parsing: Integer.parseInt("2A", 16)
// 3. String reconstruction: new StringBuilder().append("Sec").append("ret").toString()
// 4. Arithmetic and bitwise expression folding: 10 * 5 + 4
// 5. Constant propagation
// 6. Dead code elimination: if (false) { ... }

package com.example.security;

import java.util.Base64;

public class PayloadRunner {
    public static final String KEY_DATA = "U3VwZXJTZWNyZXRUb2tlbjIwMjY=";
    public static final int MAGIC_VAL = 10 * 5 + 4;

    public static void run() {
        String secret = new String(Base64.getDecoder().decode(KEY_DATA));
        String reconstructed = new StringBuilder().append("Sec").append("ret").toString();
        int port = Integer.parseInt("1F90", 16);

        if (false) {
            System.out.println("Dead branch that should be removed");
        }

        System.out.println(secret);
        System.out.println(reconstructed);
        System.out.println(MAGIC_VAL);
        System.out.println(port);
    }
}
