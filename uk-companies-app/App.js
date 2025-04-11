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
} from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { API_URL } from './config';

// Stack navigator
const Stack = createStackNavigator();

// Home Screen Component
const HomeScreen = ({ navigation }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [page, setPage] = useState(1);
  const [totalResults, setTotalResults] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

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
      Alert.alert(
        'Download Started',
        'Downloading and importing Companies House data. This may take several minutes.'
      );

      const response = await fetch(`${API_URL}/download`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error('Download failed');
      }

      const data = await response.json();
      Alert.alert('Success', data.message);
    } catch (error) {
      Alert.alert('Error', error.message);
    } finally {
      setIsDownloading(false);
    }
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

        <TouchableOpacity
          style={[styles.downloadButton, isDownloading && styles.disabledButton]}
          onPress={downloadCompaniesData}
          disabled={isDownloading}
        >
          <Text style={styles.buttonText}>
            {isDownloading ? 'Downloading...' : 'Download Company Data'}
          </Text>
        </TouchableOpacity>

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

          {/* Display each address field separately for more control */}
          {company.registered_office_address && (
            <View style={styles.addressDetailContainer}>
              <Text style={styles.addressDetailTitle}>Address Details:</Text>

              {company.registered_office_address.care_of && (
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>Care Of:</Text>
                  <Text style={styles.detailValue}>{company.registered_office_address.care_of}</Text>
                </View>
              )}

              {company.registered_office_address.po_box && (
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>PO Box:</Text>
                  <Text style={styles.detailValue}>{company.registered_office_address.po_box}</Text>
                </View>
              )}

              {company.registered_office_address.address_line_1 && (
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>Address Line 1:</Text>
                  <Text style={styles.detailValue}>{company.registered_office_address.address_line_1}</Text>
                </View>
              )}

              {company.registered_office_address.address_line_2 && (
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>Address Line 2:</Text>
                  <Text style={styles.detailValue}>{company.registered_office_address.address_line_2}</Text>
                </View>
              )}

              {company.registered_office_address.town && (
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>Town:</Text>
                  <Text style={styles.detailValue}>{company.registered_office_address.town}</Text>
                </View>
              )}

              {company.registered_office_address.county && (
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>County:</Text>
                  <Text style={styles.detailValue}>{company.registered_office_address.county}</Text>
                </View>
              )}

              {company.registered_office_address.country && (
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>Country:</Text>
                  <Text style={styles.detailValue}>{company.registered_office_address.country}</Text>
                </View>
              )}

              {company.registered_office_address.postcode && (
                <View style={styles.detailItem}>
                  <Text style={styles.detailLabel}>Postcode:</Text>
                  <Text style={styles.detailValue}>{company.registered_office_address.postcode}</Text>
                </View>
              )}
            </View>
          )}
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
  downloadButton: {
    backgroundColor: '#3498db',
    padding: 12,
    margin: 16,
    borderRadius: 5,
    alignItems: 'center',
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
  addressDetailContainer: {
    marginTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#e0e0e0',
    paddingTop: 16,
  },
  addressDetailTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 12,
    color: '#2c3e50',
  },
});