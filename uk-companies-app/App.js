import React, { useState, useEffect } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  RefreshControl,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Modal,
} from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { API_URL } from './config';

// Stack navigator
const Stack = createStackNavigator();

// Cross-platform progress bar component
const ProgressBar = ({ progress, color }) => {
  return (
    <View style={styles.progressBarContainer}>
      <View style={[styles.progressBarFill, { width: `${progress * 100}%`, backgroundColor: color }]} />
    </View>
  );
};

// Download Status Component
const DownloadStatusModal = ({ visible, status, onClose }) => {
  const getStatusColor = () => {
    switch (status?.status) {
      case 'downloading':
        return '#3498db';
      case 'processing':
        return '#f39c12';
      case 'completed':
        return '#2ecc71';
      case 'failed':
        return '#e74c3c';
      default:
        return '#95a5a6';
    }
  };

  const formatTime = (timeString) => {
    if (!timeString) return 'N/A';
    try {
      const date = new Date(timeString);
      return date.toLocaleTimeString();
    } catch (e) {
      return timeString;
    }
  };

  const getStatusMessage = () => {
    if (!status) return "No status available";

    switch (status.status) {
      case 'downloading':
        return "Downloading data from Companies House...";
      case 'processing':
        return `Processing data... (${status.processed_records.toLocaleString()} of ${status.total_records.toLocaleString()} records)`;
      case 'completed':
        return "Download and import completed successfully!";
      case 'failed':
        return `Error: ${status.error || "Unknown error"}`;
      default:
        return "Preparing download...";
    }
  };

  if (!visible) return null;

  return (
    <Modal
      visible={visible}
      transparent={true}
      animationType="slide"
      onRequestClose={onClose}
    >
      <View style={styles.modalOverlay}>
        <View style={styles.modalContent}>
          <Text style={styles.modalTitle}>Download Status</Text>

          <View style={styles.statusContainer}>
            <Text style={[styles.statusText, { color: getStatusColor() }]}>
              {status?.status?.toUpperCase() || 'LOADING'}
            </Text>

            <Text style={styles.statusMessage}>{getStatusMessage()}</Text>

            {status?.start_time && (
              <Text style={styles.statusDetail}>Started at: {formatTime(status.start_time)}</Text>
            )}

            <View style={styles.progressContainer}>
              {/* Cross-platform progress bar */}
              <ProgressBar
                progress={status?.completion_percentage / 100 || 0}
                color={getStatusColor()}
              />
              <Text style={styles.progressText}>
                {Math.round(status?.completion_percentage || 0)}%
              </Text>
            </View>

            {status?.total_records > 0 && (
              <Text style={styles.statusDetail}>
                Records: {status.processed_records.toLocaleString()} / {status.total_records.toLocaleString()}
              </Text>
            )}
          </View>

          <TouchableOpacity
            style={[
              styles.modalButton,
              status?.status === 'completed' || status?.status === 'failed'
                ? styles.closeButton
                : styles.disabledButton
            ]}
            onPress={onClose}
            disabled={status?.status !== 'completed' && status?.status !== 'failed'}
          >
            <Text style={styles.buttonText}>
              {status?.status === 'completed' || status?.status === 'failed' ? 'Close' : 'Running...'}
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
};

// Home Screen Component
const HomeScreen = ({ navigation }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState(null);
  const [statusModalVisible, setStatusModalVisible] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [page, setPage] = useState(1);
  const [totalResults, setTotalResults] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [pollingInterval, setPollingInterval] = useState(null);

  useEffect(() => {
    // Clean up polling on unmount
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [pollingInterval]);

  const startStatusPolling = () => {
    // Clear any existing interval first
    if (pollingInterval) {
      clearInterval(pollingInterval);
    }

    // Check status immediately
    fetchDownloadStatus();

    // Then start polling
    const interval = setInterval(() => {
      fetchDownloadStatus();
    }, 2000); // Poll every 2 seconds

    setPollingInterval(interval);
  };

  const stopStatusPolling = () => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      setPollingInterval(null);
    }
  };

  const fetchDownloadStatus = async () => {
    try {
      const response = await fetch(`${API_URL}/download/status`);

      if (!response.ok) {
        throw new Error('Failed to fetch status');
      }

      const status = await response.json();
      setDownloadStatus(status);

      // If the download is no longer running, stop polling
      if (!status.is_running && (status.status === 'completed' || status.status === 'failed')) {
        stopStatusPolling();
        setIsDownloading(false);
      }
    } catch (error) {
      console.error('Error fetching status:', error);
    }
  };

  const searchCompanies = async (query, pageNum = 1, refresh = false) => {
    if (!query.trim()) {
      return;
    }

    try {
      setIsLoading(true);
      const response = await fetch(
        `${API_URL}/search?query=${encodeURIComponent(query)}&page=${pageNum}&per_page=20`
      );

      if (!response.ok) {
        throw new Error('Search failed');
      }

      const data = await response.json();

      if (refresh || pageNum === 1) {
        setCompanies(data.companies);
      } else {
        setCompanies([...companies, ...data.companies]);
      }

      setTotalResults(data.total);
      setPage(pageNum);
    } catch (error) {
      Alert.alert('Error', error.message);
    } finally {
      setIsLoading(false);
      setRefreshing(false);
    }
  };

  const downloadCompaniesData = async () => {
    try {
      setIsDownloading(true);

      const response = await fetch(`${API_URL}/download`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error('Download failed to start');
      }

      const data = await response.json();

      // Start polling for status updates
      startStatusPolling();

      // Show the status modal
      setStatusModalVisible(true);

    } catch (error) {
      // Use alert for web compatibility
      if (Platform.OS === 'web') {
        window.alert(`Error: ${error.message}`);
      } else {
        Alert.alert('Error', error.message);
      }
      setIsDownloading(false);
    }
  };

  const closeStatusModal = () => {
    setStatusModalVisible(false);
    // Only stop polling if download is complete or failed
    if (downloadStatus && (downloadStatus.status === 'completed' || downloadStatus.status === 'failed')) {
      stopStatusPolling();
    }
  };

  const showCurrentStatus = () => {
    fetchDownloadStatus();
    setStatusModalVisible(true);
  };

  const onRefresh = () => {
    setRefreshing(true);
    searchCompanies(searchQuery, 1, true);
  };

  const renderCompanyItem = ({ item }) => (
    <TouchableOpacity
      style={styles.companyItem}
      onPress={() => navigation.navigate('CompanyDetails', { companyNumber: item.company_number })}
    >
      <Text style={styles.companyName}>{item.company_name}</Text>
      <Text style={styles.companyNumber}>Company Number: {item.company_number}</Text>
      <Text style={styles.companyStatus}>Status: {item.company_status || 'N/A'}</Text>
      {item.registered_office_address && item.registered_office_address.postcode && (
        <Text style={styles.companyPostcode}>
          Postcode: {item.registered_office_address.postcode}
        </Text>
      )}
    </TouchableOpacity>
  );

  const loadMoreCompanies = () => {
    if (companies.length < totalResults && !isLoading) {
      searchCompanies(searchQuery, page + 1);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
      >
        <View style={styles.searchContainer}>
          <TextInput
            style={styles.searchInput}
            placeholder="Search companies..."
            value={searchQuery}
            onChangeText={setSearchQuery}
            onSubmitEditing={() => searchCompanies(searchQuery)}
          />
          <TouchableOpacity
            style={styles.searchButton}
            onPress={() => searchCompanies(searchQuery)}
          >
            <Text style={styles.buttonText}>Search</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.downloadContainer}>
          <TouchableOpacity
            style={[styles.downloadButton, isDownloading && styles.disabledButton]}
            onPress={downloadCompaniesData}
            disabled={isDownloading}
          >
            <Text style={styles.buttonText}>
              {isDownloading ? 'Downloading...' : 'Download Company Data'}
            </Text>
          </TouchableOpacity>

          {isDownloading && (
            <TouchableOpacity
              style={styles.statusButton}
              onPress={showCurrentStatus}
            >
              <Text style={styles.buttonText}>Show Status</Text>
            </TouchableOpacity>
          )}
        </View>

        {totalResults > 0 && (
          <Text style={styles.resultsCount}>
            Found {totalResults} companies
          </Text>
        )}

        <FlatList
          data={companies}
          renderItem={renderCompanyItem}
          keyExtractor={(item) => item.company_number}
          contentContainerStyle={styles.listContainer}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
          onEndReached={loadMoreCompanies}
          onEndReachedThreshold={0.2}
          ListFooterComponent={
            isLoading && companies.length > 0 ? (
              <ActivityIndicator size="large" color="#0000ff" />
            ) : null
          }
          ListEmptyComponent={
            !isLoading ? (
              <Text style={styles.emptyList}>
                No companies found. Try searching for a company name or number.
              </Text>
            ) : (
              <ActivityIndicator size="large" color="#0000ff" />
            )
          }
        />

        <DownloadStatusModal
          visible={statusModalVisible}
          status={downloadStatus}
          onClose={closeStatusModal}
        />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

// Format address helper function
const formatAddress = (address) => {
  if (!address) return 'N/A';

  const addressParts = [];

  if (address.care_of) addressParts.push(`c/o ${address.care_of}`);
  if (address.po_box) addressParts.push(`PO Box ${address.po_box}`);
  if (address.address_line_1) addressParts.push(address.address_line_1);
  if (address.address_line_2) addressParts.push(address.address_line_2);
  if (address.town) addressParts.push(address.town);
  if (address.county) addressParts.push(address.county);
  if (address.country) addressParts.push(address.country);
  if (address.postcode) addressParts.push(address.postcode);

  return addressParts.join('\n');
};

// Company Details Screen Component
const CompanyDetailsScreen = ({ route }) => {
  const { companyNumber } = route.params;
  const [company, setCompany] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchCompanyDetails = async () => {
      try {
        setIsLoading(true);
        const response = await fetch(`${API_URL}/company/${companyNumber}`);

        if (!response.ok) {
          throw new Error('Failed to fetch company details');
        }

        const data = await response.json();
        setCompany(data);
      } catch (error) {
        setError(error.message);
      } finally {
        setIsLoading(false);
      }
    };

    fetchCompanyDetails();
  }, [companyNumber]);

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#0000ff" />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.errorText}>Error: {error}</Text>
      </View>
    );
  }

  if (!company) {
    return (
      <View style={styles.centerContainer}>
        <Text>Company not found</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView>
        <View style={styles.detailsContainer}>
          <Text style={styles.detailsTitle}>{company.company_name}</Text>

          <View style={styles.detailItem}>
            <Text style={styles.detailLabel}>Company Number:</Text>
            <Text style={styles.detailValue}>{company.company_number}</Text>
          </View>

          <View style={styles.detailItem}>
            <Text style={styles.detailLabel}>Status:</Text>
            <Text style={styles.detailValue}>{company.company_status || 'N/A'}</Text>
          </View>

          <View style={styles.detailItem}>
            <Text style={styles.detailLabel}>Category:</Text>
            <Text style={styles.detailValue}>{company.company_category || 'N/A'}</Text>
          </View>

          <View style={styles.detailItem}>
            <Text style={styles.detailLabel}>Country of Origin:</Text>
            <Text style={styles.detailValue}>{company.country_of_origin || 'N/A'}</Text>
          </View>

          <View style={styles.detailItem}>
            <Text style={styles.detailLabel}>Incorporation Date:</Text>
            <Text style={styles.detailValue}>{company.incorporation_date || 'N/A'}</Text>
          </View>

          <View style={styles.detailItem}>
            <Text style={styles.detailLabel}>SIC Codes:</Text>
            <Text style={styles.detailValue}>{company.sic_codes || 'N/A'}</Text>
          </View>

          <View style={styles.addressContainer}>
            <Text style={styles.detailLabel}>Registered Office Address:</Text>
            <Text style={styles.addressValue}>
              {formatAddress(company.registered_office_address)}
            </Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
};

// Main App Component
export default function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName="Home"
        screenOptions={{
          headerStyle: {
            backgroundColor: '#2c3e50',
          },
          headerTintColor: '#fff',
          headerTitleStyle: {
            fontWeight: 'bold',
          },
        }}
      >
        <Stack.Screen
          name="Home"
          component={HomeScreen}
          options={{ title: 'UK Companies Search' }}
        />
        <Stack.Screen
          name="CompanyDetails"
          component={CompanyDetailsScreen}
          options={{ title: 'Company Details' }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8f9fa',
  },
  keyboardView: {
    flex: 1,
  },
  searchContainer: {
    flexDirection: 'row',
    padding: 16,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  searchInput: {
    flex: 1,
    height: 40,
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 5,
    paddingHorizontal: 10,
    marginRight: 8,
  },
  searchButton: {
    backgroundColor: '#2c3e50',
    borderRadius: 5,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 15,
  },
  downloadContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 16,
  },
  downloadButton: {
    backgroundColor: '#3498db',
    padding: 12,
    borderRadius: 5,
    alignItems: 'center',
    flex: 1,
  },
  statusButton: {
    backgroundColor: '#f39c12',
    padding: 12,
    borderRadius: 5,
    alignItems: 'center',
    flex: 0.5,
    marginLeft: 8,
  },
  disabledButton: {
    backgroundColor: '#95a5a6',
  },
  buttonText: {
    color: '#fff',
    fontWeight: 'bold',
  },
  listContainer: {
    paddingHorizontal: 16,
    paddingBottom: 20,
  },
  companyItem: {
    backgroundColor: '#fff',
    padding: 16,
    marginVertical: 8,
    borderRadius: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
    elevation: 2,
  },
  companyName: {
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  companyNumber: {
    fontSize: 14,
    color: '#666',
  },
  companyStatus: {
    fontSize: 14,
    color: '#666',
    marginTop: 4,
  },
  companyPostcode: {
    fontSize: 14,
    color: '#666',
    marginTop: 4,
  },
  resultsCount: {
    padding: 16,
    fontStyle: 'italic',
    color: '#666',
  },
  emptyList: {
    padding: 20,
    textAlign: 'center',
    color: '#666',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  errorText: {
    color: 'red',
    textAlign: 'center',
  },
  detailsContainer: {
    padding: 16,
    backgroundColor: '#fff',
    margin: 16,
    borderRadius: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  detailsTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    marginBottom: 16,
    color: '#2c3e50',
  },
  detailItem: {
    flexDirection: 'row',
    marginBottom: 8,
    alignItems: 'flex-start',
  },
  detailLabel: {
    fontWeight: 'bold',
    width: 150,
    color: '#34495e',
  },
  detailValue: {
    flex: 1,
    color: '#2c3e50',
  },
  addressContainer: {
    marginTop: 16,
    marginBottom: 8,
  },
  addressValue: {
    marginTop: 4,
    color: '#2c3e50',
    lineHeight: 20,
  },
  // Modal styles
  modalOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
  modalContent: {
    width: '80%',
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
    elevation: 5,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 15,
    textAlign: 'center',
    color: '#2c3e50',
  },
  statusContainer: {
    alignItems: 'center',
    marginBottom: 20,
  },
  statusText: {
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 10,
  },
  statusMessage: {
    textAlign: 'center',
    marginBottom: 10,
    color: '#34495e',
  },
  statusDetail: {
    fontSize: 12,
    color: '#7f8c8d',
    marginTop: 5,
  },
  progressContainer: {
    width: '100%',
    marginVertical: 15,
    alignItems: 'center',
  },
  progressText: {
    marginTop: 5,
    fontSize: 14,
    color: '#34495e',
  },
  modalButton: {
    padding: 10,
    borderRadius: 5,
    alignItems: 'center',
    marginTop: 10,
  },
  closeButton: {
    backgroundColor: '#2ecc71',
  },
  // Custom cross-platform progress bar styles
  progressBarContainer: {
    height: 10,
    width: '100%',
    backgroundColor: '#e0e0e0',
    borderRadius: 5,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    borderRadius: 5,
  },
});