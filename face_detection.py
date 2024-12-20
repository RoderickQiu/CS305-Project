def encrypt_decrypt(text: str, key: int) -> str:
    """
    使用 XOR 算法对文本进行加密或解密。
    :param text: 原始文本
    :param key: 密钥（整数）
    :return: 加密或解密后的文本
    """
    return ''.join(chr(ord(char) ^ key) for char in text)

def main():
    key = 42  # 加密密钥

    # 输入原始文本
    original_text = input("Enter the text to encrypt: ")

    # 加密
    encrypted_text = encrypt_decrypt(original_text, key)
    print(f"Encrypted text: {encrypted_text}")

    # 解密
    decrypted_text = encrypt_decrypt(encrypted_text, key)
    print(f"Decrypted text: {decrypted_text}")

if __name__ == "__main__":
    main()
