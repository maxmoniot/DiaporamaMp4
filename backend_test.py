#!/usr/bin/env python3
"""
PhotoSync Video Creator API Test Suite
Tests all backend endpoints for the video creation application
"""

import requests
import sys
import json
import os
import time
from datetime import datetime
from pathlib import Path
from io import BytesIO
from PIL import Image

class PhotoSyncAPITester:
    def __init__(self, base_url="https://photosync-9.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.project_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details="", response_data=None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
        
        result = {
            "test": name,
            "status": "PASS" if success else "FAIL",
            "details": details,
            "response_data": response_data
        }
        self.test_results.append(result)
        print(f"{status} - {name}: {details}")
        return success

    def run_test(self, name, method, endpoint, expected_status, data=None, files=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'} if not files else {}
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                if files:
                    response = requests.post(url, files=files, data=data, timeout=60)
                else:
                    response = requests.post(url, json=data, headers=headers, timeout=60)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                return self.log_test(name, False, f"Unsupported method: {method}")

            success = response.status_code == expected_status
            details = f"Status: {response.status_code}"
            
            if success:
                try:
                    response_data = response.json()
                    self.log_test(name, True, details, response_data)
                    return True
                except:
                    self.log_test(name, True, details, {"raw_response": response.text[:200]})
                    return True
            else:
                error_details = f"Expected {expected_status}, got {response.status_code}"
                try:
                    error_data = response.json()
                    error_details += f" - {error_data}"
                except:
                    error_details += f" - {response.text[:200]}"
                self.log_test(name, False, error_details)
                return False

        except requests.exceptions.Timeout:
            self.log_test(name, False, "Request timeout")
            return False
        except requests.exceptions.ConnectionError:
            self.log_test(name, False, "Connection error - service may be down")
            return False
        except Exception as e:
            self.log_test(name, False, f"Error: {str(e)}")
            return False

    def create_test_image(self, width=800, height=600, format='JPEG'):
        """Create a test image in memory"""
        img = Image.new('RGB', (width, height), color='red')
        img_bytes = BytesIO()
        img.save(img_bytes, format=format)
        img_bytes.seek(0)
        return img_bytes

    def create_test_mp3(self):
        """Create a minimal test MP3 file (placeholder)"""
        # This creates a minimal file that looks like MP3 but won't actually work for audio analysis
        # In a real test, you'd use a proper MP3 file
        mp3_data = b'\xff\xfb\x90\x00' + b'\x00' * 1000  # MP3 header + padding
        return BytesIO(mp3_data)

    def test_root_endpoint(self):
        """Test root API endpoint"""
        return self.run_test("Root API", "GET", "", 200)

    def test_create_project(self):
        """Test project creation"""
        success = self.run_test("Create Project", "POST", "projects", 200)
        if success:
            # Get the response data from the last test result
            last_result = self.test_results[-1]
            response_data = last_result.get('response_data')
            if response_data and response_data.get('id'):
                self.project_id = response_data.get('id')
                self.log_test("Project ID Retrieved", True, f"ID: {self.project_id}")
            else:
                self.log_test("Project ID Retrieved", False, "No ID in response")
        return success

    def test_get_project(self):
        """Test getting project by ID"""
        if not self.project_id:
            return self.log_test("Get Project", False, "No project ID available")
        
        return self.run_test("Get Project", "GET", f"projects/{self.project_id}", 200)

    def test_upload_photos(self):
        """Test photo upload"""
        if not self.project_id:
            return self.log_test("Upload Photos", False, "No project ID available")
        
        # Create test images
        test_images = [
            ('files', ('test1.jpg', self.create_test_image(), 'image/jpeg')),
            ('files', ('test2.png', self.create_test_image(format='PNG'), 'image/png'))
        ]
        
        url = f"{self.base_url}/projects/{self.project_id}/photos"
        try:
            response = requests.post(url, files=test_images, timeout=60)
            success = response.status_code == 200
            
            if success:
                try:
                    data = response.json()
                    uploaded_count = data.get('uploaded', 0)
                    details = f"Status: 200, Uploaded: {uploaded_count} photos"
                    return self.log_test("Upload Photos", True, details, data)
                except:
                    return self.log_test("Upload Photos", True, "Status: 200, Response not JSON")
            else:
                error_details = f"Expected 200, got {response.status_code}"
                try:
                    error_data = response.json()
                    error_details += f" - {error_data}"
                except:
                    error_details += f" - {response.text[:200]}"
                return self.log_test("Upload Photos", False, error_details)
                
        except Exception as e:
            return self.log_test("Upload Photos", False, f"Error: {str(e)}")

    def test_upload_music(self):
        """Test music upload"""
        if not self.project_id:
            return self.log_test("Upload Music", False, "No project ID available")
        
        # Create test MP3 file
        test_mp3 = ('file', ('test_music.mp3', self.create_test_mp3(), 'audio/mpeg'))
        
        url = f"{self.base_url}/projects/{self.project_id}/music"
        try:
            response = requests.post(url, files=[test_mp3], timeout=60)
            success = response.status_code == 200
            
            if success:
                try:
                    data = response.json()
                    tempo = data.get('tempo', 'N/A')
                    duration = data.get('duration', 'N/A')
                    details = f"Status: 200, Tempo: {tempo} BPM, Duration: {duration}s"
                    return self.log_test("Upload Music", True, details, data)
                except:
                    return self.log_test("Upload Music", True, "Status: 200, Response not JSON")
            else:
                error_details = f"Expected 200, got {response.status_code}"
                try:
                    error_data = response.json()
                    error_details += f" - {error_data}"
                except:
                    error_details += f" - {response.text[:200]}"
                return self.log_test("Upload Music", False, error_details)
                
        except Exception as e:
            return self.log_test("Upload Music", False, f"Error: {str(e)}")

    def test_sync_to_beats(self):
        """Test syncing photos to music beats"""
        if not self.project_id:
            return self.log_test("Sync to Beats", False, "No project ID available")
        
        return self.run_test("Sync to Beats", "POST", f"projects/{self.project_id}/sync-to-beats", 200)

    def test_update_settings(self):
        """Test updating project settings"""
        if not self.project_id:
            return self.log_test("Update Settings", False, "No project ID available")
        
        settings_data = {
            "format": "vertical",
            "resolution": "720p",
            "transition": "fade",
            "global_rhythm_multiplier": 2.0
        }
        
        return self.run_test("Update Settings", "PUT", f"projects/{self.project_id}/settings", 200, settings_data)

    def test_reorder_photos(self):
        """Test reordering photos"""
        if not self.project_id:
            return self.log_test("Reorder Photos", False, "No project ID available")
        
        # First get the project to see if we have photos
        try:
            response = requests.get(f"{self.base_url}/projects/{self.project_id}")
            if response.status_code == 200:
                project_data = response.json()
                photos = project_data.get('photos', [])
                if len(photos) >= 2:
                    # Reverse the order of first two photos
                    photo_ids = [photos[1]['id'], photos[0]['id']] + [p['id'] for p in photos[2:]]
                    reorder_data = {"photo_ids": photo_ids}
                    return self.run_test("Reorder Photos", "PUT", f"projects/{self.project_id}/photos/reorder", 200, reorder_data)
                else:
                    return self.log_test("Reorder Photos", False, "Need at least 2 photos to test reordering")
            else:
                return self.log_test("Reorder Photos", False, "Could not fetch project data")
        except Exception as e:
            return self.log_test("Reorder Photos", False, f"Error: {str(e)}")

    def test_export_start(self):
        """Test starting video export"""
        if not self.project_id:
            return self.log_test("Start Export", False, "No project ID available")
        
        return self.run_test("Start Export", "POST", f"projects/{self.project_id}/export", 200)

    def test_export_status(self):
        """Test getting export status"""
        if not self.project_id:
            return self.log_test("Export Status", False, "No project ID available")
        
        return self.run_test("Export Status", "GET", f"projects/{self.project_id}/export/status", 200)

    def test_static_file_endpoints(self):
        """Test static file serving endpoints"""
        # These will likely return 404 since we don't have real files, but we test the endpoint structure
        
        # Test photo endpoint
        success1 = self.run_test("Get Photo (404 expected)", "GET", "photos/nonexistent.jpg", 404)
        
        # Test thumbnail endpoint  
        success2 = self.run_test("Get Thumbnail (404 expected)", "GET", "thumbnails/nonexistent.jpg", 404)
        
        return success1 and success2

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting PhotoSync API Test Suite")
        print(f"📡 Testing API at: {self.base_url}")
        print("=" * 60)
        
        # Basic connectivity
        if not self.test_root_endpoint():
            print("❌ Root endpoint failed - API may be down")
            return False
        
        # Project lifecycle tests
        self.test_create_project()
        self.test_get_project()
        
        # Media upload tests
        self.test_upload_photos()
        self.test_upload_music()
        
        # Project manipulation tests
        self.test_sync_to_beats()
        self.test_update_settings()
        self.test_reorder_photos()
        
        # Export tests
        self.test_export_start()
        time.sleep(2)  # Wait a bit before checking status
        self.test_export_status()
        
        # Static file tests
        self.test_static_file_endpoints()
        
        # Print summary
        print("=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return True
        else:
            print("⚠️  Some tests failed - check details above")
            failed_tests = [r for r in self.test_results if r['status'] == 'FAIL']
            print(f"❌ Failed tests: {[t['test'] for t in failed_tests]}")
            return False

def main():
    """Main test execution"""
    tester = PhotoSyncAPITester()
    
    try:
        success = tester.run_all_tests()
        
        # Save detailed results
        results_file = "/app/test_reports/backend_api_results.json"
        with open(results_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "total_tests": tester.tests_run,
                "passed_tests": tester.tests_passed,
                "success_rate": f"{(tester.tests_passed/tester.tests_run*100):.1f}%" if tester.tests_run > 0 else "0%",
                "test_results": tester.test_results
            }, f, indent=2)
        
        print(f"📄 Detailed results saved to: {results_file}")
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"💥 Test suite error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())