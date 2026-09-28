// Sample obfuscated JavaScript file (Phase 6)
// Combines multiple obfuscation layers:
// 1. Base64 encoded string with atob
// 2. String.fromCharCode character code sequences
// 3. Array join string reconstruction
// 4. String reversal idiom
// 5. Computed bracket property notation
// 6. IIFE wrapper
// 7. Constant propagation and arithmetic folding

var authHeader = atob('QmVhcmVyIHRva2VuX3NlY3JldF8xMjM0NQ==');
var appName = String.fromCharCode(85, 110, 105, 118, 101, 114, 115, 97, 108);
var appSuffix = [' ', 'D', 'e', 'o', 'b', 'f', 'u', 's', 'c', 'a', 't', 'o', 'r'].join('');
var fullAppName = appName + appSuffix;

var targetStatus = 'kO'.split('').reverse().join('');
var baseOffset = 100 + 20 * 5;
var flag = (function(offset) {
    return offset + 50;
})(baseOffset);

console['log'](fullAppName, authHeader, targetStatus, flag);
