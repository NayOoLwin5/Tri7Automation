# Ensure you have androguard installed:
# pip install androguard

from androguard.core.apk import APK

class APKAnalyzer:
    def __init__(self, apk_path):
        self.apk_path = apk_path
        self.apk = APK(apk_path)

    def get_package_name(self):
        return self.apk.get_package()

    def get_version_code(self):
        return self.apk.get_androidversion_code()

    def get_version_name(self):
        return self.apk.get_androidversion_name()

    def get_permissions(self):
        return self.apk.get_permissions()

    def get_metadata(self):
        return {
            "package_name": self.get_package_name(),
            "version_code": self.get_version_code(),
            "version_name": self.get_version_name(),
            "permissions": self.get_permissions()
        }

# Example usage:
if __name__ == "__main__":
    apk_path = "/Users/innolabs/Downloads/ayapay.apk"
    analyzer = APKAnalyzer(apk_path)
    metadata = analyzer.get_metadata()
    print(metadata)