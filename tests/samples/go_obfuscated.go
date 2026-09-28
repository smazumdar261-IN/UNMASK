// Sample obfuscated Go file (Phase 9)
// Combines multiple obfuscation layers:
// 1. Base64 decoder: base64.StdEncoding.DecodeString(...)
// 2. Integer parsing: strconv.ParseInt("1F90", 16, 64)
// 3. String reconstruction: string([]byte{...}) and strings.Join(...)
// 4. Arithmetic and bitwise expression folding: 10 * 5 + 4
// 5. Constant propagation
// 6. Dead code elimination: if false { ... }

package main

import (
	"encoding/base64"
	"fmt"
	"strconv"
	"strings"
)

const KeyData = "U3VwZXJTZWNyZXRUb2tlbjIwMjY="
const MagicVal = 10 * 5 + 4

func main() {
	secretBytes, _ := base64.StdEncoding.DecodeString(KeyData)
	secret := string(secretBytes)
	reconstructed := strings.Join([]string{"Sec", "ret"}, "")
	langName := string([]byte{71, 111, 108, 97, 110, 103})
	port, _ := strconv.ParseInt("1F90", 16, 64)

	if false {
		fmt.Println("Dead branch that should be removed")
	}

	fmt.Println(secret)
	fmt.Println(reconstructed)
	fmt.Println(langName)
	fmt.Println(MagicVal)
	fmt.Println(port)
}
