#include <codecvt>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <locale>
#include <string>

#include "../src/api/CZIeditAPI.h"
#include "../src/api/inc_libCzi.h"

static int test_open_close_and_read_xml(const std::wstring &path) {
  CZIeditAPI editor(path);
  if (!editor.IsOpen()) {
    std::cerr << "Editor not open\n";
    return 1;
  }
  auto xml = editor.ReadMetadataXml();
  if (xml.find("<ImageDocument") == std::string::npos) {
    std::cerr << "Root missing\n";
    return 2;
  }
  editor.Close();
  if (editor.IsOpen()) {
    std::cerr << "Editor still open\n";
    return 3;
  }
  return 0;
}

static int test_commit_title_change(const std::wstring &srcPath) {
  auto tmp = std::filesystem::temp_directory_path() / "cziedit_tmp1.czi";
  std::error_code ec;
  std::filesystem::copy_file(
      srcPath, tmp, std::filesystem::copy_options::overwrite_existing, ec);
  if (ec) {
    std::cerr << "Copy failed: " << ec.message() << "\n";
    return 10;
  }

  CZIeditAPI editor(tmp.wstring());
  auto builder = editor.CreateMetadataBuilder();
  libCZI::GeneralDocumentInfo gdi;
  gdi.SetTitle(L"NativeCommitted");
  builder->SetGeneralDocumentInfo(gdi);
  if (!builder->CanCommit()) {
    std::cerr << "CanCommit false\n";
    return 11;
  }
  builder->Commit();
  editor.Close();

  CZIeditAPI editor2(tmp.wstring());
  auto xml = editor2.ReadMetadataXml();
  if (xml.find("<Title>NativeCommitted</Title>") == std::string::npos) {
    std::cerr << "Title not committed\n";
    return 12;
  }
  return 0;
}

static int test_channel_info(const std::wstring &srcPath) {
  auto tmp = std::filesystem::temp_directory_path() / "cziedit_tmp2.czi";
  std::error_code ec;
  std::filesystem::copy_file(
      srcPath, tmp, std::filesystem::copy_options::overwrite_existing, ec);
  if (ec) {
    std::cerr << "Copy failed: " << ec.message() << "\n";
    return 10;
  }

  CZIeditAPI editor(tmp.wstring());
  auto builder = editor.CreateMetadataBuilder();
  ChannelDisplaySettingsStructWithNameAndDescription expected;
  expected.Clear();
  expected.name = L"Native channel";
  expected.description = L"Native display-settings round trip";
  builder->GetRootNode()
      ->GetOrCreateChildNode("Metadata/DisplaySetting/Channels/Channel")
      ->SetAttribute(L"Id", L"Channel:0");
  builder->SetDisplaySettings({{0, expected}});
  builder->Commit();
  auto displaySettings = editor.ReadDisplaySettings();
  if (displaySettings.size() != 1 || displaySettings.at(0).name != expected.name ||
      displaySettings.at(0).description != expected.description) {
    std::cerr << "Display settings did not round trip\n";
    return 20;
  }

  return 0;
}

static int test_custom_attribute(const std::wstring &srcPath) {
  auto tmp = std::filesystem::temp_directory_path() / "cziedit_tmp3.czi";
  std::error_code ec;
  std::filesystem::copy_file(
      srcPath, tmp, std::filesystem::copy_options::overwrite_existing, ec);
  if (ec) {
    std::cerr << "Copy failed: " << ec.message() << "\n";
    return 10;
  }

  CZIeditAPI editor(tmp.wstring());

  auto builder = editor.CreateMetadataBuilder();
  auto customValue = editor.ReadCustomKeyValue("Blah");
  std::cout << "Original custom value for 'Blah': type="
            << static_cast<int>(customValue.GetType()) << "\n";
  builder->SetCustomKeyValue("Blah", libCZI::CustomValueVariant("BlahBlah"));
  builder->Commit();
  auto setVar = editor.ReadCustomKeyValue("Blah");
  if (setVar.GetAsStringOrThrow() != "BlahBlah") {
    std::cerr << "Custom attribute did not round trip\n";
    return 30;
  }
  return 0;
}

int main(int argc, char *argv[]) {
  if (argc != 2) {
    std::cerr << "Usage: cziedit_tests image.czi\n";
    return 100;
  }
  std::wstring_convert<std::codecvt_utf8_utf16<wchar_t>> converter;
  const std::wstring path = converter.from_bytes(argv[1]);

  const auto run = [&path](const char *name, auto test) {
    std::cerr << "[ RUN ] " << name << std::endl;
    try {
      const int result = test(path);
      std::cerr << (result == 0 ? "[ OK ] " : "[ FAILED ] ") << name
                << " (" << result << ")" << std::endl;
      return result;
    } catch (const std::exception &error) {
      std::cerr << "[ EXCEPTION ] " << name << ": " << error.what()
                << std::endl;
      return 101;
    } catch (...) {
      std::cerr << "[ EXCEPTION ] " << name << ": unknown exception"
                << std::endl;
      return 102;
    }
  };
  int rc = 0;
  rc |= run("open_close_and_read_xml", test_open_close_and_read_xml);
  rc |= run("commit_title_change", test_commit_title_change);
  rc |= run("channel_info", test_channel_info);
  rc |= run("custom_attribute", test_custom_attribute);
  if (rc != 0)
    std::cerr << "One or more editor tests failed.\n";
  return rc;
}
