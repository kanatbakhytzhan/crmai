# 📱 Flutter / React Native Integration Guide

## 🚀 Быстрый старт для мобильной разработки

---

## 📡 BASE URL

```dart
// Flutter
const String BASE_URL = "http://192.168.0.10:8000";

// React Native
const BASE_URL = "http://192.168.0.10:8000";
```

⚠️ **ВАЖНО:** Замените `192.168.0.10` на IP вашего компьютера!

---

## 🔐 Аутентификация

### 1. Login (получение токена)

**Flutter:**
```dart
import 'package:http/http.dart' as http;
import 'dart:convert';

Future<String> login(String email, String password) async {
  final response = await http.post(
    Uri.parse('$BASE_URL/api/auth/login'),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'username=$email&password=$password',
  );
  
  if (response.statusCode == 200) {
    final data = jsonDecode(response.body);
    return data['access_token'];
  } else {
    throw Exception('Login failed');
  }
}
```

**React Native:**
```javascript
const login = async (email, password) => {
  const response = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `username=${email}&password=${password}`
  });
  
  const data = await response.json();
  return data.access_token;
};
```

---

## 📋 Работа с заявками

### 2. Получить список заявок

**Flutter:**
```dart
class Lead {
  final int id;
  final String name;
  final String phone;
  final String city;
  final String objectType;
  final String area;
  final String summary;
  final String status;
  final DateTime createdAt;
  
  Lead.fromJson(Map<String, dynamic> json)
    : id = json['id'],
      name = json['name'],
      phone = json['phone'],
      city = json['city'] ?? '',
      objectType = json['object_type'] ?? '',
      area = json['area'] ?? '',
      summary = json['summary'] ?? '',
      status = json['status'],
      createdAt = DateTime.parse(json['created_at']);
}

Future<List<Lead>> getLeads(String token) async {
  final response = await http.get(
    Uri.parse('$BASE_URL/api/leads'),
    headers: {'Authorization': 'Bearer $token'},
  );
  
  if (response.statusCode == 200) {
    final data = jsonDecode(utf8.decode(response.bodyBytes));
    return (data['leads'] as List)
        .map((json) => Lead.fromJson(json))
        .toList();
  } else {
    throw Exception('Failed to load leads');
  }
}
```

**React Native:**
```javascript
const getLeads = async (token) => {
  const response = await fetch(`${BASE_URL}/api/leads`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const data = await response.json();
  return data.leads;
};
```

---

### 3. Получить одну заявку

**Flutter:**
```dart
Future<Lead> getLead(String token, int leadId) async {
  final response = await http.get(
    Uri.parse('$BASE_URL/api/leads/$leadId'),
    headers: {'Authorization': 'Bearer $token'},
  );
  
  if (response.statusCode == 200) {
    return Lead.fromJson(jsonDecode(utf8.decode(response.bodyBytes)));
  } else {
    throw Exception('Lead not found');
  }
}
```

**React Native:**
```javascript
const getLead = async (token, leadId) => {
  const response = await fetch(`${BASE_URL}/api/leads/${leadId}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  return await response.json();
};
```

---

### 4. Обновить статус заявки

**Flutter:**
```dart
Future<void> updateLeadStatus(String token, int leadId, String status) async {
  final response = await http.patch(
    Uri.parse('$BASE_URL/api/leads/$leadId'),
    headers: {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    },
    body: jsonEncode({'status': status}),
  );
  
  if (response.statusCode != 200) {
    throw Exception('Failed to update status');
  }
}

// Использование:
await updateLeadStatus(token, 1, 'in_progress');
await updateLeadStatus(token, 1, 'success');
await updateLeadStatus(token, 1, 'failed');
```

**React Native:**
```javascript
const updateLeadStatus = async (token, leadId, status) => {
  await fetch(`${BASE_URL}/api/leads/${leadId}`, {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ status })
  });
};

// Использование:
await updateLeadStatus(token, 1, 'in_progress');
await updateLeadStatus(token, 1, 'success');
await updateLeadStatus(token, 1, 'failed');
```

---

### 5. Удалить заявку

**Flutter:**
```dart
Future<void> deleteLead(String token, int leadId) async {
  final response = await http.delete(
    Uri.parse('$BASE_URL/api/leads/$leadId'),
    headers: {'Authorization': 'Bearer $token'},
  );
  
  if (response.statusCode != 200) {
    throw Exception('Failed to delete lead');
  }
}
```

**React Native:**
```javascript
const deleteLead = async (token, leadId) => {
  await fetch(`${BASE_URL}/api/leads/${leadId}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` }
  });
};
```

---

## 🎨 UI Компоненты

### Flutter: Статусный Badge

```dart
Widget buildStatusBadge(String status) {
  Color color;
  String text;
  
  switch (status) {
    case 'new':
      color = Colors.blue;
      text = 'Новая';
      break;
    case 'in_progress':
      color = Colors.orange;
      text = 'В работе';
      break;
    case 'done':
    case 'success':
      color = Colors.green;
      text = 'Успешно';
      break;
    case 'cancelled':
    case 'failed':
      color = Colors.red;
      text = 'Отказ';
      break;
    default:
      color = Colors.grey;
      text = status;
  }
  
  return Container(
    padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    decoration: BoxDecoration(
      color: color.withOpacity(0.2),
      borderRadius: BorderRadius.circular(16),
    ),
    child: Text(
      text,
      style: TextStyle(color: color, fontWeight: FontWeight.bold),
    ),
  );
}
```

### React Native: Статусный Badge

```javascript
const StatusBadge = ({ status }) => {
  const getStatusConfig = (status) => {
    switch (status) {
      case 'new':
        return { color: '#3B82F6', text: 'Новая' };
      case 'in_progress':
        return { color: '#F59E0B', text: 'В работе' };
      case 'done':
      case 'success':
        return { color: '#10B981', text: 'Успешно' };
      case 'cancelled':
      case 'failed':
        return { color: '#EF4444', text: 'Отказ' };
      default:
        return { color: '#6B7280', text: status };
    }
  };
  
  const { color, text } = getStatusConfig(status);
  
  return (
    <View style={{
      backgroundColor: `${color}20`,
      paddingHorizontal: 12,
      paddingVertical: 6,
      borderRadius: 16
    }}>
      <Text style={{ color, fontWeight: 'bold' }}>{text}</Text>
    </View>
  );
};
```

---

## 🔐 Хранение токена

### Flutter (SharedPreferences)

```dart
import 'package:shared_preferences/shared_preferences.dart';

class AuthService {
  static const String _tokenKey = 'auth_token';
  
  Future<void> saveToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
  }
  
  Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey);
  }
  
  Future<void> deleteToken() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }
}
```

### React Native (AsyncStorage)

```javascript
import AsyncStorage from '@react-native-async-storage/async-storage';

const saveToken = async (token) => {
  await AsyncStorage.setItem('auth_token', token);
};

const getToken = async () => {
  return await AsyncStorage.getItem('auth_token');
};

const deleteToken = async () => {
  await AsyncStorage.removeItem('auth_token');
};
```

---

## 📱 Полный пример экрана списка заявок

### Flutter

```dart
class LeadsScreen extends StatefulWidget {
  @override
  _LeadsScreenState createState() => _LeadsScreenState();
}

class _LeadsScreenState extends State<LeadsScreen> {
  List<Lead> leads = [];
  bool isLoading = true;
  
  @override
  void initState() {
    super.initState();
    loadLeads();
  }
  
  Future<void> loadLeads() async {
    setState(() => isLoading = true);
    
    try {
      final token = await AuthService().getToken();
      if (token != null) {
        final fetchedLeads = await getLeads(token);
        setState(() {
          leads = fetchedLeads;
          isLoading = false;
        });
      }
    } catch (e) {
      setState(() => isLoading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Ошибка загрузки: $e'))
      );
    }
  }
  
  Future<void> changeStatus(int leadId, String newStatus) async {
    try {
      final token = await AuthService().getToken();
      if (token != null) {
        await updateLeadStatus(token, leadId, newStatus);
        await loadLeads(); // Перезагрузить список
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Статус обновлен'))
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Ошибка: $e'))
      );
    }
  }
  
  @override
  Widget build(BuildContext context) {
    if (isLoading) {
      return Scaffold(
        appBar: AppBar(title: Text('Заявки')),
        body: Center(child: CircularProgressIndicator()),
      );
    }
    
    return Scaffold(
      appBar: AppBar(
        title: Text('Заявки (${leads.length})'),
        actions: [
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed: loadLeads,
          )
        ],
      ),
      body: RefreshIndicator(
        onRefresh: loadLeads,
        child: ListView.builder(
          itemCount: leads.length,
          itemBuilder: (context, index) {
            final lead = leads[index];
            return Card(
              margin: EdgeInsets.all(8),
              child: ListTile(
                title: Text(lead.name),
                subtitle: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('📞 ${lead.phone}'),
                    Text('📍 ${lead.city} • ${lead.objectType}'),
                  ],
                ),
                trailing: buildStatusBadge(lead.status),
                onTap: () {
                  // Открыть детали заявки
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (context) => LeadDetailScreen(leadId: lead.id),
                    ),
                  );
                },
              ),
            );
          },
        ),
      ),
    );
  }
}
```

---

## ✅ Чеклист для интеграции:

- [ ] Установить `http` пакет (Flutter) или настроить `fetch` (React Native)
- [ ] Заменить `BASE_URL` на IP вашего компьютера
- [ ] Реализовать login/logout
- [ ] Хранить JWT токен в SecureStorage
- [ ] Реализовать экран списка заявок
- [ ] Реализовать экран деталей заявки
- [ ] Добавить кнопки изменения статуса
- [ ] Добавить Pull-to-Refresh
- [ ] Обработать ошибки (401, 404, 500)
- [ ] Добавить индикаторы загрузки

---

## 🚀 Готово!

API полностью готов к интеграции с мобильным приложением!

**Swagger для тестирования:** http://192.168.0.10:8000/docs
